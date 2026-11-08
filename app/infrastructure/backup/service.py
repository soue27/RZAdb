from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.engine import URL, make_url

from app.core.config import Settings

logger = logging.getLogger(__name__)

_LIBPQ_QUERY_KEYS = {
    "application_name",
    "channel_binding",
    "connect_timeout",
    "dbname",
    "gssencmode",
    "host",
    "hostaddr",
    "krbsrvname",
    "load_balance_hosts",
    "options",
    "port",
    "require_auth",
    "service",
    "sslcert",
    "sslcrl",
    "sslcrldir",
    "sslkey",
    "sslmode",
    "sslrootcert",
    "ssl_min_protocol_version",
    "ssl_max_protocol_version",
    "target_session_attrs",
    "user",
}


class BackupError(RuntimeError):
    """Base error for a failed local database backup."""


class BackupDisabledError(BackupError):
    """Raised when backup execution is disabled in configuration."""


class BackupConfigurationError(BackupError):
    """Raised when backup configuration is invalid or unsupported."""


class BackupOperationError(BackupError):
    def __init__(
        self,
        message: str,
        *,
        run_id: UUID,
        manifest_path: Path | None,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.manifest_path = manifest_path


class _BackupStepError(RuntimeError):
    """An error message safe to persist in a manifest and logs."""


@dataclass(frozen=True)
class BackupResult:
    run_id: UUID
    dump_path: Path
    manifest_path: Path
    size_bytes: int
    sha256: str
    duration_seconds: float


@dataclass(frozen=True)
class _ConnectionInfo:
    database_uri: str
    password: str | None


class LocalPostgresBackupService:
    """Create, validate, publish and retain local PostgreSQL custom dumps."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_backup(self) -> BackupResult:
        if not self.settings.backup_enabled:
            raise BackupDisabledError("Database backup is disabled")
        if not self.settings.backup_local_enabled:
            raise BackupConfigurationError(
                "No backup channel is enabled; local storage is disabled"
            )

        backup_dir = self.settings.backup_local_dir
        run_id = uuid4()
        started_at = datetime.now(UTC)
        started_clock = time.monotonic()
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"rzadb_{timestamp}_{run_id.hex}"
        dump_path = backup_dir / f"{stem}.dump"
        manifest_path = backup_dir / f"{stem}.json"
        temporary_dump: Path | None = None
        published_dump = False
        stage = "prepare local backup directory"
        manifest: dict[str, Any] = {
            "run_id": str(run_id),
            "started_at": started_at.isoformat(),
            "dump_filename": dump_path.name,
            "size_bytes": None,
            "sha256": None,
            "duration_seconds": 0.0,
            "dump_created": False,
            "pg_restore_list_validation": "not_run",
            "local_storage": {"enabled": True, "status": "pending"},
            "status": "running",
            "error": None,
        }

        try:
            backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(backup_dir, 0o700)

            stage = "locate PostgreSQL utilities"
            pg_dump = shutil.which("pg_dump")
            if pg_dump is None:
                raise BackupConfigurationError("pg_dump utility was not found")
            pg_restore = shutil.which("pg_restore")
            if pg_restore is None:
                raise BackupConfigurationError("pg_restore utility was not found")

            stage = "parse DATABASE_URL"
            connection = self._connection_info(self.settings.database_url)
            command_env = self._child_environment(connection.password)

            stage = "create temporary custom-format dump"
            temporary_dump = self._new_temporary_file(backup_dir, stem, ".dump.tmp")
            dump_command = [
                pg_dump,
                "-Fc",
                "--no-password",
                f"--dbname={connection.database_uri}",
                "--file",
                str(temporary_dump),
            ]
            dump_process = subprocess.run(
                dump_command,
                env=command_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
            )
            if dump_process.returncode != 0:
                raise _BackupStepError(
                    f"pg_dump exited with status {dump_process.returncode}"
                )
            if not temporary_dump.is_file():
                raise _BackupStepError("pg_dump did not create a dump file")
            size_bytes = temporary_dump.stat().st_size
            if size_bytes <= 0:
                raise _BackupStepError("pg_dump created an empty dump file")
            manifest["dump_created"] = True

            stage = "validate dump with pg_restore --list"
            restore_process = subprocess.run(
                [pg_restore, "--list", str(temporary_dump)],
                env=command_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
            )
            if restore_process.returncode != 0:
                raise _BackupStepError(
                    f"pg_restore --list exited with status {restore_process.returncode}"
                )
            manifest["pg_restore_list_validation"] = "passed"

            stage = "calculate SHA-256"
            sha256 = self._sha256(temporary_dump)
            size_bytes = temporary_dump.stat().st_size
            manifest["size_bytes"] = size_bytes
            manifest["sha256"] = sha256

            stage = "publish dump atomically"
            with temporary_dump.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary_dump, dump_path)
            temporary_dump = None
            published_dump = True
            os.chmod(dump_path, 0o600)
            manifest["local_storage"]["status"] = "success"
            manifest["status"] = "success"
            manifest["duration_seconds"] = round(
                time.monotonic() - started_clock, 6
            )

            stage = "write success manifest atomically"
            self._write_manifest_atomic(manifest_path, manifest, stem)

            try:
                self._apply_retention(backup_dir)
            except Exception as exc:
                logger.warning(
                    "Backup run %s succeeded but retention failed (%s)",
                    run_id,
                    type(exc).__name__,
                )
            return BackupResult(
                run_id=run_id,
                dump_path=dump_path,
                manifest_path=manifest_path,
                size_bytes=size_bytes,
                sha256=sha256,
                duration_seconds=manifest["duration_seconds"],
            )
        except Exception as exc:
            self._remove_temporary(temporary_dump)
            if published_dump:
                self._remove_temporary(dump_path)
            safe_error = self._safe_error(stage, exc)
            manifest["status"] = "failed"
            manifest["error"] = safe_error
            manifest["local_storage"]["status"] = "failed"
            manifest["duration_seconds"] = round(
                time.monotonic() - started_clock, 6
            )
            try:
                backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(backup_dir, 0o700)
                self._write_manifest_atomic(manifest_path, manifest, stem)
            except Exception as manifest_exc:
                logger.error(
                    "Backup run %s failed in %s (%s); failure manifest could not be written (%s)",
                    run_id,
                    stage,
                    type(exc).__name__,
                    type(manifest_exc).__name__,
                )
                raise BackupOperationError(
                    f"{safe_error}; failure manifest could not be written",
                    run_id=run_id,
                    manifest_path=None,
                ) from None
            logger.error(
                "Backup run %s failed in %s (%s)",
                run_id,
                stage,
                type(exc).__name__,
            )
            raise BackupOperationError(
                safe_error,
                run_id=run_id,
                manifest_path=manifest_path,
            ) from None
        finally:
            self._remove_temporary(temporary_dump)

    @staticmethod
    def _connection_info(database_url: str) -> _ConnectionInfo:
        try:
            url = make_url(database_url)
        except Exception:
            raise BackupConfigurationError("DATABASE_URL is invalid") from None
        if not url.drivername.startswith("postgresql"):
            raise BackupConfigurationError(
                "DATABASE_URL must use a PostgreSQL driver"
            )

        query = {key.lower(): value for key, value in url.query.items()}
        query_password = query.pop("password", None)
        unsupported_secrets = [key for key in query if "password" in key]
        if unsupported_secrets:
            raise BackupConfigurationError(
                "DATABASE_URL contains an unsupported password parameter"
            )

        ssl = query.pop("ssl", None)
        timeout = query.pop("timeout", None)
        unsupported_options = set(query) - _LIBPQ_QUERY_KEYS
        if unsupported_options:
            raise BackupConfigurationError(
                "DATABASE_URL contains unsupported connection parameters: "
                + ", ".join(sorted(unsupported_options))
            )
        libpq_query = {
            key: value
            for key, value in query.items()
            if key in _LIBPQ_QUERY_KEYS
        }
        if timeout is not None and "connect_timeout" not in libpq_query:
            libpq_query["connect_timeout"] = timeout
        if ssl is not None and "sslmode" not in libpq_query:
            ssl_value = str(ssl).lower()
            if ssl_value in {"true", "1", "require"}:
                libpq_query["sslmode"] = "require"
            elif ssl_value in {"false", "0", "disable"}:
                libpq_query["sslmode"] = "disable"
            elif ssl_value in {"verify-ca", "verify-full", "prefer", "allow"}:
                libpq_query["sslmode"] = ssl_value
            else:
                raise BackupConfigurationError(
                    "DATABASE_URL contains an unsupported SSL parameter"
                )

        try:
            libpq_url: URL = URL.create(
                drivername="postgresql",
                username=url.username,
                host=url.host,
                port=url.port,
                database=url.database,
                query=libpq_query,
            )
            uri = libpq_url.render_as_string(hide_password=True)
        except Exception:
            raise BackupConfigurationError(
                "DATABASE_URL could not be converted for PostgreSQL utilities"
            ) from None
        password = url.password
        if password is None and query_password is not None:
            password = str(query_password)
        return _ConnectionInfo(database_uri=uri, password=password)

    @staticmethod
    def _child_environment(password: str | None) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("PGPASSWORD", None)
        if password:
            environment["PGPASSWORD"] = password
        return environment

    @staticmethod
    def _new_temporary_file(directory: Path, stem: str, suffix: str) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix=f".{stem}.",
            suffix=suffix,
            dir=directory,
            delete=False,
        ) as temporary:
            path = Path(temporary.name)
        try:
            os.chmod(path, 0o600)
        except OSError:
            path.unlink(missing_ok=True)
            raise
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as dump_file:
            for block in iter(lambda: dump_file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _remove_temporary(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Backup file cleanup failed (%s)", type(exc).__name__)

    @staticmethod
    def _write_manifest_atomic(
        manifest_path: Path,
        manifest: dict[str, Any],
        stem: str,
    ) -> None:
        temporary_path = LocalPostgresBackupService._new_temporary_file(
            manifest_path.parent, stem, ".json.tmp"
        )
        try:
            with temporary_path.open("w", encoding="utf-8") as manifest_file:
                json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
                manifest_file.write("\n")
                manifest_file.flush()
                os.fsync(manifest_file.fileno())
            os.replace(temporary_path, manifest_path)
            os.chmod(manifest_path, 0o600)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _safe_error(stage: str, error: Exception) -> str:
        if isinstance(error, (BackupConfigurationError, BackupDisabledError)):
            return str(error)
        if isinstance(error, _BackupStepError):
            return str(error)
        return f"{stage} failed ({type(error).__name__})"

    def _apply_retention(self, backup_dir: Path) -> None:
        successful: list[tuple[str, Path, Path]] = []
        for manifest_path in backup_dir.glob("rzadb_*.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                dump_name = manifest.get("dump_filename")
                dump_path = backup_dir / dump_name
                if (
                    manifest.get("status") != "success"
                    or manifest.get("dump_created") is not True
                    or manifest.get("pg_restore_list_validation") != "passed"
                    or manifest.get("local_storage", {}).get("status") != "success"
                    or dump_path.parent != backup_dir
                    or not dump_path.is_file()
                ):
                    continue
                successful.append(
                    (str(manifest.get("started_at", "")), dump_path, manifest_path)
                )
            except (OSError, ValueError, TypeError, AttributeError):
                continue

        successful.sort(key=lambda item: item[0], reverse=True)
        for _, dump_path, manifest_path in successful[
            self.settings.backup_local_retention_count :
        ]:
            try:
                dump_path.unlink()
                manifest_path.unlink()
            except OSError as exc:
                logger.warning(
                    "Backup retention could not remove an old pair (%s)",
                    type(exc).__name__,
                )
