from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.infrastructure.backup.dump import DumpCreationError, PostgresDumpService

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
        "backup_local_dir": tmp_path,
    }
    values.update(overrides)
    return Settings(**values)


def successful_processes(monkeypatch, *, dump_bytes=b"valid custom dump"):
    calls = []
    monkeypatch.setattr(
        "app.infrastructure.backup.dump.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0].endswith("pg_dump"):
            Path(command[command.index("--file") + 1]).write_bytes(dump_bytes)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("app.infrastructure.backup.dump.subprocess.run", run)
    return calls


def test_creates_custom_dump_validates_hash_and_keeps_password_out_of_args(
    tmp_path, monkeypatch
):
    calls = successful_processes(monkeypatch)
    artifact = PostgresDumpService(make_settings(tmp_path)).create_dump(
        backup_dir=tmp_path,
        stem="run",
    )

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
    assert artifact.size_bytes == len(b"valid custom dump")
    assert artifact.sha256 == hashlib.sha256(b"valid custom dump").hexdigest()
    assert artifact.path.read_bytes() == b"valid custom dump"


def test_asyncpg_url_conversion_preserves_ssl_connection_options(tmp_path):
    service = PostgresDumpService(make_settings(tmp_path))
    connection = service._connection_info(service.settings.database_url)
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
    ("query", "key", "value"),
    [
        ("ssl=true", "sslmode", "require"),
        ("ssl=false", "sslmode", "disable"),
        ("timeout=12", "connect_timeout", "12"),
    ],
)
def test_asyncpg_ssl_and_timeout_parameters_are_mapped(
    tmp_path, query, key, value
):
    service = PostgresDumpService(make_settings(tmp_path))
    connection = service._connection_info(
        f"postgresql+asyncpg://u:p@localhost/db?{query}"
    )
    assert make_url(connection.database_uri).query[key] == value


def test_query_password_is_moved_to_environment_only(tmp_path):
    connection = PostgresDumpService._connection_info(
        "postgresql+asyncpg://user@localhost/db?password=query-secret&sslmode=require"
    )
    assert connection.password == "query-secret"
    assert "query-secret" not in connection.database_uri


@pytest.mark.parametrize(
    ("which", "expected"),
    [
        ({"pg_dump": None, "pg_restore": "/usr/bin/pg_restore"}, "pg_dump"),
        ({"pg_dump": "/usr/bin/pg_dump", "pg_restore": None}, "pg_restore"),
    ],
)
def test_missing_postgres_utility_is_reported_and_has_no_temp_file(
    tmp_path, monkeypatch, which, expected
):
    monkeypatch.setattr(
        "app.infrastructure.backup.dump.shutil.which", lambda name: which[name]
    )
    with pytest.raises(DumpCreationError, match=expected):
        PostgresDumpService(make_settings(tmp_path)).create_dump(
            backup_dir=tmp_path, stem="run"
        )
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("dump_bytes", [None, b""])
def test_missing_or_empty_dump_fails_and_removes_temporary_file(
    tmp_path, monkeypatch, dump_bytes
):
    successful_processes(monkeypatch, dump_bytes=dump_bytes or b"")
    if dump_bytes is None:
        def remove_dump_then_succeed(command, **kwargs):
            Path(command[command.index("--file") + 1]).unlink()
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(
            "app.infrastructure.backup.dump.subprocess.run", remove_dump_then_succeed
        )
    with pytest.raises(DumpCreationError):
        PostgresDumpService(make_settings(tmp_path)).create_dump(
            backup_dir=tmp_path, stem="run"
        )
    assert not list(tmp_path.glob("*.tmp"))


def test_nonzero_pg_dump_exit_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.backup.dump.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    def fail_dump(command, **kwargs):
        Path(command[command.index("--file") + 1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr("app.infrastructure.backup.dump.subprocess.run", fail_dump)
    with pytest.raises(DumpCreationError, match="status 2"):
        PostgresDumpService(make_settings(tmp_path)).create_dump(
            backup_dir=tmp_path, stem="run"
        )
    assert not list(tmp_path.glob("*.tmp"))


def test_nonzero_pg_restore_exit_reports_created_but_unvalidated_dump(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.infrastructure.backup.dump.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )

    def fail_restore(command, **kwargs):
        if command[0].endswith("pg_dump"):
            Path(command[command.index("--file") + 1]).write_bytes(b"valid dump")
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr("app.infrastructure.backup.dump.subprocess.run", fail_restore)
    with pytest.raises(DumpCreationError) as error:
        PostgresDumpService(make_settings(tmp_path)).create_dump(
            backup_dir=tmp_path, stem="run"
        )
    assert error.value.dump_created is True
    assert error.value.validation_status == "failed"
    assert not list(tmp_path.glob("*.tmp"))


def test_sha256_error_cleans_temporary_dump(tmp_path, monkeypatch):
    successful_processes(monkeypatch)
    monkeypatch.setattr(
        PostgresDumpService,
        "_sha256",
        staticmethod(lambda _path: (_ for _ in ()).throw(OSError())),
    )
    with pytest.raises(DumpCreationError, match="calculate SHA-256 failed"):
        PostgresDumpService(make_settings(tmp_path)).create_dump(
            backup_dir=tmp_path, stem="run"
        )
    assert not list(tmp_path.glob("*.tmp"))
