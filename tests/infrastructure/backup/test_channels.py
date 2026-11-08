from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.backup.channels import (
    ChannelConfigurationError,
    EmailBackupChannel,
    LocalBackupChannel,
    YandexDiskBackupChannel,
)
from app.infrastructure.backup.dump import DumpArtifact


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://user:password@localhost/rzadb",
        "session_secret": "test-secret",
        "backup_enabled": True,
        "backup_local_dir": tmp_path,
        "backup_local_retention_count": 2,
        "backup_yandex_disk_token": SecretStr("disk-test-token"),
        "backup_yandex_disk_folder": "/RZAdb/backups",
        "backup_yandex_disk_retention_count": 2,
    }
    values.update(overrides)
    return Settings(**values)


def successful_manifest(dump_path: Path, started_at: str) -> Path:
    manifest_path = dump_path.with_suffix(".json")
    manifest_path.write_text(
        json.dumps({
            "started_at": started_at,
            "dump_filename": dump_path.name,
            "dump_created": True,
            "pg_restore_list_validation": "passed",
            "channels": {"local": {"status": "success"}},
            "local_storage": {"status": "success"},
            "status": "partial_success",
        }),
        encoding="utf-8",
    )
    return manifest_path


def test_local_channel_atomically_publishes_dump(tmp_path):
    source = tmp_path / ".temporary.dump"
    source.write_bytes(b"dump")
    artifact = DumpArtifact(source, 4, "hash")
    target = LocalBackupChannel(make_settings(tmp_path)).publish(
        artifact, "rzadb_20261108T010203000000Z_0123456789abcdef0123456789abcdef.dump"
    )

    assert target.read_bytes() == b"dump"
    assert not source.exists()


def test_local_retention_keeps_latest_successful_pairs_and_ignores_failed_runs(
    tmp_path,
):
    older = tmp_path / (
        "rzadb_20260101T000000000000Z_00000000000000000000000000000001.dump"
    )
    newer = tmp_path / (
        "rzadb_20260102T000000000000Z_00000000000000000000000000000002.dump"
    )
    newest = tmp_path / (
        "rzadb_20260103T000000000000Z_00000000000000000000000000000003.dump"
    )
    failed = tmp_path / (
        "rzadb_20260104T000000000000Z_00000000000000000000000000000004.dump"
    )
    for path in (older, newer, newest, failed):
        path.write_bytes(b"dump")
    old_manifest = successful_manifest(older, "2026-01-01T00:00:00+00:00")
    successful_manifest(newer, "2026-01-02T00:00:00+00:00")
    newest_manifest = successful_manifest(newest, "2026-01-03T00:00:00+00:00")
    failed_manifest = failed.with_suffix(".json")
    failed_manifest.write_text(
        json.dumps({
            "dump_filename": failed.name,
            "dump_created": True,
            "pg_restore_list_validation": "passed",
            "channels": {"local": {"status": "failed"}},
            "status": "failed",
        }),
        encoding="utf-8",
    )

    LocalBackupChannel(make_settings(tmp_path, backup_local_retention_count=2)).apply_retention()

    assert not older.exists() and not old_manifest.exists()
    assert newer.exists()
    assert newest.exists() and newest_manifest.exists()
    assert failed.exists() and failed_manifest.exists()


def test_email_channel_requires_explicit_recipient(tmp_path):
    channel = EmailBackupChannel(make_settings(tmp_path, backup_email_to=None))
    with pytest.raises(ChannelConfigurationError, match="BACKUP_EMAIL_TO"):
        channel.validate()


@pytest.mark.asyncio
async def test_email_channel_includes_backup_metadata_and_attachment(tmp_path, monkeypatch):
    settings = make_settings(
        tmp_path,
        backup_email_to="superadmin@example.com",
    )
    channel = EmailBackupChannel(settings)
    captured = {}

    class FakeSender:
        async def send(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "app.infrastructure.backup.channels.SMTPEmailSender",
        lambda _settings: FakeSender(),
    )
    channel.validate()
    dump_path = tmp_path / "backup.dump"
    dump_path.write_bytes(b"dump")

    result = await channel.send(
        dump_path=dump_path,
        run_id="run-123",
        started_at="2026-11-08T10:11:12+00:00",
        size_bytes=4,
        sha256="deadbeef",
        dump_name="rzadb_20261108T101112000000Z_0123456789abcdef0123456789abcdef.dump",
    )

    assert result.status == "success"
    assert captured["to"] == "superadmin@example.com"
    assert dump_path in captured["attachments"]
    assert captured["attachment_name"] == (
        "rzadb_20261108T101112000000Z_0123456789abcdef0123456789abcdef.dump"
    )
    assert "2026-11-08T10:11:12+00:00" in captured["subject"]
    for value in ("run-123", "4 bytes", "deadbeef"):
        assert value in captured["body"]


class FakeYandexHttpClient:
    def __init__(self, files):
        self.files = files
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, url, *, params, headers):
        self.calls.append(("get", url, params, headers))
        if url.endswith("/upload"):
            self.uploaded_name = params["path"].rsplit("/", 1)[-1]
            return self._response(
                200, url, {"href": "https://upload.example/signed"}
            )
        if params.get("fields"):
            return self._response(
                200,
                url,
                {"_embedded": {
                    "items": [*self.files, {"name": self.uploaded_name, "type": "file"}],
                    "total": len(self.files) + 1,
                }},
            )
        return self._response(200, url, {"type": "dir"})

    def put(self, url, *, params=None, headers=None, content=None):
        self.calls.append(("put", url, params, headers, content))
        if url.startswith("https://upload.example/"):
            payload = b"".join(content)
            self.uploaded_payload = payload
        return self._response(201, str(url), {})

    def delete(self, url, *, params, headers):
        self.calls.append(("delete", url, params, headers))
        return self._response(202, url, {})

    @staticmethod
    def _response(status_code, url, payload):
        return httpx.Response(
            status_code,
            json=payload,
            request=httpx.Request("GET", str(url)),
        )


def test_yandex_upload_streams_file_and_retains_only_its_backup_files(
    tmp_path, monkeypatch
):
    names = [
        "rzadb_20260101T000000000000Z_00000000000000000000000000000001.dump",
        "rzadb_20260102T000000000000Z_00000000000000000000000000000002.dump",
        "unrelated.dump",
    ]
    client = FakeYandexHttpClient(
        [{"name": name, "type": "file"} for name in names]
    )
    monkeypatch.setattr(
        "app.infrastructure.backup.channels.httpx.Client",
        lambda **kwargs: client,
    )
    dump_path = tmp_path / (
        "rzadb_20261108T010203000000Z_0123456789abcdef0123456789abcdef.dump"
    )
    dump_path.write_bytes(b"stream this dump")
    channel = YandexDiskBackupChannel(make_settings(tmp_path))

    result = channel.upload(dump_path, dump_path.name)

    assert result.status == "success"
    assert result.path == f"/RZAdb/backups/{dump_path.name}"
    assert result.retention_status == "success"
    upload_calls = [call for call in client.calls if call[0] == "put" and call[1].startswith("https://")]
    assert len(upload_calls) == 1
    assert "Authorization" not in (upload_calls[0][3] or {})
    assert client.uploaded_payload == b"stream this dump"
    deletions = [call for call in client.calls if call[0] == "delete"]
    assert len(deletions) == 1
    assert deletions[0][2]["path"].endswith(names[0])
    assert deletions[0][2]["permanently"] == "true"


def test_yandex_channel_requires_token(tmp_path):
    channel = YandexDiskBackupChannel(
        make_settings(tmp_path, backup_yandex_disk_token=None)
    )
    with pytest.raises(ChannelConfigurationError, match="BACKUP_YANDEX_DISK_TOKEN"):
        channel.validate()
