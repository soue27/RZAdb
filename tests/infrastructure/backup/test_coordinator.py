from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.backup.channels import ChannelResult
from app.infrastructure.backup.coordinator import (
    BackupCoordinator,
    BackupManifestError,
)
from app.infrastructure.backup.dump import DumpArtifact, DumpCreationError, PostgresDumpService
from app.infrastructure.backup.channels import LocalBackupChannel


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://user:password@localhost/rzadb",
        "session_secret": "test-secret",
        "backup_enabled": True,
        "backup_local_enabled": True,
        "backup_local_dir": tmp_path,
        "backup_local_retention_count": 2,
        "backup_email_enabled": False,
        "backup_email_to": None,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "sender@example.com",
        "smtp_password": "smtp-secret",
        "smtp_from_email": "sender@example.com",
        "smtp_starttls": True,
        "smtp_use_ssl": False,
        "backup_yandex_disk_enabled": False,
        "backup_yandex_disk_token": SecretStr("disk-token"),
    }
    values.update(overrides)
    return Settings(**values)


def install_dump(monkeypatch, dump_bytes=b"verified dump"):
    def create_dump(self, *, backup_dir, stem):
        path = backup_dir / f".{stem}.dump.tmp"
        path.write_bytes(dump_bytes)
        return DumpArtifact(
            path=path,
            size_bytes=len(dump_bytes),
            sha256="test-sha256",
        )

    monkeypatch.setattr(PostgresDumpService, "create_dump", create_dump)


@pytest.mark.asyncio
async def test_channels_run_sequentially_and_one_delivery_error_does_not_block_others(
    tmp_path, monkeypatch
):
    install_dump(monkeypatch)
    settings = make_settings(
        tmp_path,
        backup_email_enabled=True,
        backup_email_to="superadmin@example.com",
        backup_yandex_disk_enabled=True,
    )
    calls = []
    original_publish = LocalBackupChannel.publish

    def publish_local(self, artifact, dump_name):
        calls.append(("local", dump_name))
        return original_publish(self, artifact, dump_name)

    monkeypatch.setattr(LocalBackupChannel, "publish", publish_local)

    async def fail_email(self, **kwargs):
        calls.append(("email", kwargs))
        raise RuntimeError("SMTP error containing a private response")

    def deliver_to_yandex(self, path, name):
        calls.append(("yandex_disk", path, name))
        assert path.is_file()
        return ChannelResult("success", path=f"/RZAdb/backups/{name}")

    monkeypatch.setattr("app.infrastructure.backup.coordinator.EmailBackupChannel.send", fail_email)
    monkeypatch.setattr(
        "app.infrastructure.backup.coordinator.YandexDiskBackupChannel.upload",
        deliver_to_yandex,
    )

    result = await BackupCoordinator(settings).run()

    assert [call[0] for call in calls] == ["local", "email", "yandex_disk"]
    assert result["status"] == "partial_success"
    assert result["channels"]["local"]["status"] == "success"
    assert result["channels"]["email"]["status"] == "failed"
    assert "private response" not in result["channels"]["email"]["error"]
    assert result["channels"]["yandex_disk"]["status"] == "success"
    assert Path(result["dump_path"]).is_file()
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["channels"]["email"]["status"] == "failed"
    assert manifest["channels"]["yandex_disk"]["status"] == "success"
    assert manifest["local_storage"]["status"] == "success"


@pytest.mark.asyncio
async def test_email_channel_missing_recipient_does_not_block_local_backup(
    tmp_path, monkeypatch
):
    install_dump(monkeypatch)
    settings = make_settings(
        tmp_path,
        backup_email_enabled=True,
        backup_email_to=None,
    )
    email_called = False

    async def send_email(self, **kwargs):
        nonlocal email_called
        email_called = True

    monkeypatch.setattr("app.infrastructure.backup.coordinator.EmailBackupChannel.send", send_email)

    result = await BackupCoordinator(settings).run()

    assert result["status"] == "partial_success"
    assert result["channels"]["email"]["status"] == "failed"
    assert "BACKUP_EMAIL_TO" in result["channels"]["email"]["error"]
    assert not email_called
    assert Path(result["dump_path"]).is_file()


@pytest.mark.asyncio
async def test_yandex_missing_token_does_not_block_local_backup(tmp_path, monkeypatch):
    install_dump(monkeypatch)
    settings = make_settings(
        tmp_path,
        backup_yandex_disk_enabled=True,
        backup_yandex_disk_token=None,
    )
    result = await BackupCoordinator(settings).run()

    assert result["status"] == "partial_success"
    assert result["channels"]["local"]["status"] == "success"
    assert result["channels"]["yandex_disk"]["status"] == "failed"
    assert "BACKUP_YANDEX_DISK_TOKEN" in result["channels"]["yandex_disk"]["error"]


@pytest.mark.asyncio
async def test_remote_only_run_saves_manifest_locally_but_not_the_dump(
    tmp_path, monkeypatch
):
    install_dump(monkeypatch)
    settings = make_settings(
        tmp_path,
        backup_local_enabled=False,
        backup_yandex_disk_enabled=True,
    )
    delivered = []

    def upload(self, path, dump_name):
        delivered.append(path)
        assert path.is_file()
        return ChannelResult("success", path=f"/RZAdb/backups/{dump_name}")

    monkeypatch.setattr(
        "app.infrastructure.backup.coordinator.YandexDiskBackupChannel.upload",
        upload,
    )

    result = await BackupCoordinator(settings).run()

    assert result["status"] == "success"
    assert result["dump_path"] is None
    assert result["channels"]["local"]["status"] == "disabled"
    assert Path(result["manifest_path"]).is_file()
    assert not list(tmp_path.glob("*.dump"))
    assert len(delivered) == 1
    assert not delivered[0].exists()


@pytest.mark.asyncio
async def test_final_manifest_write_error_is_separate_and_keeps_local_dump(
    tmp_path, monkeypatch, caplog
):
    install_dump(monkeypatch)
    settings = make_settings(tmp_path)

    def fail_manifest(path, manifest):
        raise OSError("filesystem failed")

    monkeypatch.setattr(BackupCoordinator, "_write_manifest_atomic", staticmethod(fail_manifest))

    with pytest.raises(BackupManifestError, match="manifest write failed"):
        await BackupCoordinator(settings).run()

    published_dumps = list(tmp_path.glob("rzadb_*.dump"))
    assert len(published_dumps) == 1
    assert "manifest write failed" in caplog.text
    assert "Backup channel local failed" not in caplog.text


@pytest.mark.asyncio
async def test_dump_failure_is_manifested_and_channels_are_not_attempted(
    tmp_path, monkeypatch
):
    def fail_dump(self, *, backup_dir, stem):
        raise DumpCreationError(
            "pg_restore --list exited with status 1",
            dump_created=True,
            validation_status="failed",
        )

    monkeypatch.setattr(PostgresDumpService, "create_dump", fail_dump)
    settings = make_settings(tmp_path, backup_email_enabled=True, backup_email_to=None)

    result = await BackupCoordinator(settings).run()

    assert result["status"] == "failed"
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["dump_created"] is True
    assert manifest["pg_restore_list_validation"] == "failed"
    assert manifest["channels"]["local"]["status"] == "not_attempted"
    assert manifest["channels"]["email"]["status"] == "failed"
    assert not list(tmp_path.glob("*.dump"))
