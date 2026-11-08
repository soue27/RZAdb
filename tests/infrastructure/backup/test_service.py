from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.infrastructure.backup.service import (
    BackupConfigurationError,
    BackupDisabledError,
    BackupOperationError,
    LocalPostgresBackupService,
)

DB_PASSWORD = "do-not-log-this-password"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": (
            f"postgresql+asyncpg://backup_user:{DB_PASSWORD}"
            "@db.example:5544/rzadb?sslmode=verify-full&sslrootcert=%2Ftmp%2Fca.pem"
        ),
        "session_secret": "test-secret",
        "backup_enabled": True,
        "backup_local_enabled": True,
        "backup_local_dir": tmp_path,
        "backup_local_retention_count": 5,
    }
    values.update(overrides)
    return Settings(**values)


def install_successful_utilities(monkeypatch, *, dump_bytes=b"valid custom dump"):
    calls = []
    monkeypatch.setattr(
        "app.infrastructure.backup.service.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0].endswith("pg_dump"):
            output_path = Path(command[command.index("--file") + 1])
            output_path.write_bytes(dump_bytes)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("app.infrastructure.backup.service.subprocess.run", run)
    return calls


def read_manifest(result) -> dict:
    return json.loads(result.manifest_path.read_text(encoding="utf-8"))


def write_successful_pair(directory: Path, name: str, started_at: datetime) -> tuple[Path, Path]:
    dump_path = directory / f"rzadb_{name}.dump"
    manifest_path = directory / f"rzadb_{name}.json"
    dump_path.write_bytes(b"previous valid dump")
    manifest_path.write_text(
        json.dumps({
            "run_id": name,
            "started_at": started_at.isoformat(),
            "dump_filename": dump_path.name,
            "dump_created": True,
            "pg_restore_list_validation": "passed",
            "local_storage": {"status": "success"},
            "status": "success",
        }),
        encoding="utf-8",
    )
    return dump_path, manifest_path


def test_successful_custom_backup_passes_safe_arguments_and_writes_manifest(
    tmp_path, monkeypatch
):
    calls = install_successful_utilities(monkeypatch)
    service = LocalPostgresBackupService(make_settings(tmp_path))

    result = service.create_backup()

    assert result.dump_path.is_file()
    assert result.manifest_path.is_file()
    assert result.dump_path.read_bytes() == b"valid custom dump"
    assert result.sha256 == hashlib.sha256(b"valid custom dump").hexdigest()
    assert result.size_bytes == len(b"valid custom dump")
    dump_command, dump_kwargs = calls[0]
    restore_command, restore_kwargs = calls[1]
    assert dump_command[1] == "-Fc"
    assert "--no-password" in dump_command
    assert "--file" in dump_command
    assert "--list" in restore_command
    assert DB_PASSWORD not in " ".join(dump_command)
    assert DB_PASSWORD not in " ".join(restore_command)
    assert dump_kwargs["env"]["PGPASSWORD"] == DB_PASSWORD
    assert restore_kwargs["env"]["PGPASSWORD"] == DB_PASSWORD
    assert dump_kwargs["shell"] is False
    assert restore_kwargs["shell"] is False

    manifest = read_manifest(result)
    assert UUID(manifest["run_id"]) == result.run_id
    assert manifest["started_at"].endswith("+00:00")
    assert manifest["dump_filename"] == result.dump_path.name
    assert manifest["size_bytes"] == result.size_bytes
    assert manifest["sha256"] == result.sha256
    assert manifest["duration_seconds"] >= 0
    assert manifest["dump_created"] is True
    assert manifest["pg_restore_list_validation"] == "passed"
    assert manifest["local_storage"]["status"] == "success"
    assert manifest["status"] == "success"
    serialized = result.manifest_path.read_text(encoding="utf-8")
    assert DB_PASSWORD not in serialized
    assert service.settings.database_url not in serialized
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(result.dump_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(result.manifest_path.stat().st_mode) == 0o600


def test_asyncpg_url_is_converted_to_libpq_without_dropping_ssl_options(tmp_path):
    settings = make_settings(tmp_path)
    connection = LocalPostgresBackupService._connection_info(settings.database_url)
    url = make_url(connection.database_uri)

    assert url.drivername == "postgresql"
    assert url.host == "db.example"
    assert url.port == 5544
    assert url.username == "backup_user"
    assert url.database == "rzadb"
    assert url.password is None
    assert url.query["sslmode"] == "verify-full"
    assert url.query["sslrootcert"] == "/tmp/ca.pem"
    assert connection.password == DB_PASSWORD


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ssl=true", "require"),
        ("ssl=false", "disable"),
        ("timeout=12", "12"),
    ],
)
def test_asyncpg_ssl_and_timeout_parameters_are_mapped(tmp_path, query, expected):
    url = (
        "postgresql+asyncpg://u:p@localhost/db?"
        + query
    )
    connection = LocalPostgresBackupService._connection_info(url)
    parsed = make_url(connection.database_uri)
    key = "connect_timeout" if query.startswith("timeout") else "sslmode"
    assert parsed.query[key] == expected


def test_password_in_query_is_moved_to_process_environment(tmp_path):
    connection = LocalPostgresBackupService._connection_info(
        "postgresql+asyncpg://user@localhost/db?password=query-secret&sslmode=require"
    )
    assert connection.password == "query-secret"
    assert "query-secret" not in connection.database_uri


def test_pg_dump_failure_writes_failure_manifest_and_removes_temp_files(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(
        "app.infrastructure.backup.service.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    def fail_dump(command, **kwargs):
        Path(command[command.index("--file") + 1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr("app.infrastructure.backup.service.subprocess.run", fail_dump)
    service = LocalPostgresBackupService(make_settings(tmp_path))

    with pytest.raises(BackupOperationError, match="status 2") as error:
        service.create_backup()

    assert error.value.manifest_path.is_file()
    manifest = json.loads(error.value.manifest_path.read_text())
    assert manifest["status"] == "failed"
    assert "status 2" in manifest["error"]
    assert DB_PASSWORD not in caplog.text
    assert DB_PASSWORD not in error.value.manifest_path.read_text()
    assert not list(tmp_path.glob("*.dump"))
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    ("which_result", "message"),
    [
        ({"pg_dump": None, "pg_restore": "/usr/bin/pg_restore"}, "pg_dump utility"),
        ({"pg_dump": "/usr/bin/pg_dump", "pg_restore": None}, "pg_restore utility"),
    ],
)
def test_missing_postgres_utility_is_reported(tmp_path, monkeypatch, which_result, message):
    monkeypatch.setattr(
        "app.infrastructure.backup.service.shutil.which",
        lambda name: which_result[name],
    )
    service = LocalPostgresBackupService(make_settings(tmp_path))

    with pytest.raises(BackupOperationError, match=message):
        service.create_backup()

    failed_manifests = list(tmp_path.glob("rzadb_*.json"))
    assert len(failed_manifests) == 1
    assert json.loads(failed_manifests[0].read_text())["status"] == "failed"


@pytest.mark.parametrize("dump_bytes", [None, b""])
def test_missing_or_empty_dump_is_not_published(tmp_path, monkeypatch, dump_bytes):
    calls = install_successful_utilities(monkeypatch, dump_bytes=dump_bytes or b"")
    if dump_bytes is None:
        def success_without_file(command, **kwargs):
            calls.append((command, kwargs))
            Path(command[command.index("--file") + 1]).unlink()
            return subprocess.CompletedProcess(command, 0)
        monkeypatch.setattr(
            "app.infrastructure.backup.service.subprocess.run", success_without_file
        )
    service = LocalPostgresBackupService(make_settings(tmp_path))

    with pytest.raises(BackupOperationError):
        service.create_backup()

    assert not list(tmp_path.glob("*.dump"))
    assert json.loads(next(tmp_path.glob("rzadb_*.json")).read_text())["status"] == "failed"


def test_pg_restore_failure_prevents_publication(tmp_path, monkeypatch):
    calls = install_successful_utilities(monkeypatch)
    monkeypatch.setattr(
        "app.infrastructure.backup.service.subprocess.run",
        _run_dump_then_fail_restore,
    )
    service = LocalPostgresBackupService(make_settings(tmp_path))

    with pytest.raises(BackupOperationError, match="pg_restore --list exited with status 1"):
        service.create_backup()

    assert not list(tmp_path.glob("*.dump"))
    manifest = json.loads(next(tmp_path.glob("rzadb_*.json")).read_text())
    assert manifest["pg_restore_list_validation"] == "not_run"
    assert manifest["local_storage"]["status"] == "failed"


def _run_dump_then_fail_restore(command, **kwargs):
    if command[0].endswith("pg_dump"):
        Path(command[command.index("--file") + 1]).write_bytes(b"valid dump")
        return subprocess.CompletedProcess(command, 0)
    return subprocess.CompletedProcess(command, 1)


def test_sha256_failure_does_not_publish_dump(tmp_path, monkeypatch):
    install_successful_utilities(monkeypatch)
    service = LocalPostgresBackupService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_sha256", lambda _path: (_ for _ in ()).throw(OSError()))

    with pytest.raises(BackupOperationError, match="calculate SHA-256 failed"):
        service.create_backup()

    assert not list(tmp_path.glob("*.dump"))
    assert not list(tmp_path.glob("*.tmp"))


def test_manifest_failure_removes_published_dump_and_keeps_failure_diagnostic(
    tmp_path, monkeypatch
):
    install_successful_utilities(monkeypatch)
    service = LocalPostgresBackupService(make_settings(tmp_path))
    original = service._write_manifest_atomic
    writes = 0

    def fail_first_write(path, manifest, stem):
        nonlocal writes
        writes += 1
        if writes == 1:
            raise OSError("secret value must not escape")
        original(path, manifest, stem)

    monkeypatch.setattr(service, "_write_manifest_atomic", fail_first_write)
    with pytest.raises(BackupOperationError, match="manifest atomically failed"):
        service.create_backup()

    assert writes == 2
    assert not list(tmp_path.glob("*.dump"))
    manifest = json.loads(next(tmp_path.glob("rzadb_*.json")).read_text())
    assert manifest["status"] == "failed"
    assert "secret value" not in json.dumps(manifest)


def test_dump_and_manifest_are_published_by_same_directory_atomic_replace(
    tmp_path, monkeypatch
):
    install_successful_utilities(monkeypatch)
    real_replace = os.replace
    replacements = []

    def observe_replace(source, destination):
        source, destination = Path(source), Path(destination)
        assert source.parent == destination.parent == tmp_path
        assert source.exists()
        assert not destination.exists()
        replacements.append((source.suffix, destination.suffix))
        real_replace(source, destination)

    monkeypatch.setattr("app.infrastructure.backup.service.os.replace", observe_replace)
    result = LocalPostgresBackupService(make_settings(tmp_path)).create_backup()

    assert result.dump_path.exists()
    assert result.manifest_path.exists()
    assert len(replacements) == 2


def test_retention_keeps_latest_n_successful_pairs_only(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    old_pairs = [
        write_successful_pair(tmp_path, f"old-{index}", now - timedelta(days=10 - index))
        for index in range(3)
    ]
    failed_dump = tmp_path / "rzadb_failed.dump"
    failed_manifest = tmp_path / "rzadb_failed.json"
    failed_dump.write_bytes(b"partial")
    failed_manifest.write_text(json.dumps({"status": "failed"}))
    install_successful_utilities(monkeypatch)
    service = LocalPostgresBackupService(
        make_settings(tmp_path, backup_local_retention_count=2)
    )

    result = service.create_backup()

    remaining_successful = [pair for pair in old_pairs if pair[0].exists()]
    assert len(remaining_successful) == 1
    assert result.dump_path.exists() and result.manifest_path.exists()
    assert failed_dump.exists() and failed_manifest.exists()
    assert len(list(tmp_path.glob("*.dump"))) == 3


def test_failed_new_backup_does_not_remove_previous_successful_pairs(
    tmp_path, monkeypatch
):
    previous = write_successful_pair(tmp_path, "previous", datetime.now(UTC))
    monkeypatch.setattr(
        "app.infrastructure.backup.service.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "app.infrastructure.backup.service.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1),
    )
    service = LocalPostgresBackupService(
        make_settings(tmp_path, backup_local_retention_count=1)
    )

    with pytest.raises(BackupOperationError):
        service.create_backup()

    assert previous[0].exists() and previous[1].exists()


def test_retention_error_does_not_fail_new_successful_backup(tmp_path, monkeypatch):
    old_dump, old_manifest = write_successful_pair(
        tmp_path, "old", datetime.now(UTC) - timedelta(days=1)
    )
    install_successful_utilities(monkeypatch)
    service = LocalPostgresBackupService(
        make_settings(tmp_path, backup_local_retention_count=1)
    )
    original_unlink = Path.unlink

    def fail_old_dump_unlink(path, *args, **kwargs):
        if path == old_dump:
            raise OSError("cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_old_dump_unlink)

    result = service.create_backup()

    assert result.dump_path.exists() and result.manifest_path.exists()
    assert old_dump.exists() and old_manifest.exists()


def test_invalid_database_url_is_diagnostic_and_does_not_log_secret(tmp_path, caplog):
    settings = make_settings(tmp_path, database_url=f"not-a-url-{DB_PASSWORD}")
    service = LocalPostgresBackupService(settings)

    with pytest.raises(BackupOperationError, match="DATABASE_URL is invalid"):
        service.create_backup()

    assert DB_PASSWORD not in caplog.text
    manifest = json.loads(next(tmp_path.glob("rzadb_*.json")).read_text())
    assert DB_PASSWORD not in json.dumps(manifest)


def test_backup_must_be_enabled_and_have_a_local_channel(tmp_path):
    with pytest.raises(BackupDisabledError):
        LocalPostgresBackupService(make_settings(tmp_path, backup_enabled=False)).create_backup()
    with pytest.raises(BackupConfigurationError, match="No backup channel"):
        LocalPostgresBackupService(
            make_settings(tmp_path, backup_local_enabled=False)
        ).create_backup()


@pytest.mark.parametrize("retention", [0, -1, 366])
def test_backup_retention_setting_is_validated(tmp_path, retention):
    with pytest.raises(ValidationError):
        make_settings(tmp_path, backup_local_retention_count=retention)
