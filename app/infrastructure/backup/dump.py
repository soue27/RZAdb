from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

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


class DumpCreationError(RuntimeError):
    """Безопасная диагностическая ошибка создания или проверки дампа."""

    def __init__(
        self,
        message: str,
        *,
        dump_created: bool = False,
        validation_status: str = "not_run",
    ) -> None:
        """Сохраняет настройки подключения к PostgreSQL.

        Args:
            settings: Конфигурация приложения.
        """
        super().__init__(message)
        self.dump_created = dump_created
        self.validation_status = validation_status


@dataclass
class DumpArtifact:
    """Метаданные временного дампа PostgreSQL, прошедшего проверку целостности и формата.
    """
    path: Path
    size_bytes: int
    sha256: str
    validated: bool = True

    def cleanup(self) -> None:
        """Удаляет временный файл дампа после завершения публикации или обработки ошибки.
        """
        self.path.unlink(missing_ok=True)


@dataclass(frozen=True)
class _ConnectionInfo:
    """Безопасное представление параметров подключения для PostgreSQL CLI.
    """
    database_uri: str
    password: str | None


class PostgresDumpService:
    """Создаёт временный дамп PostgreSQL в Custom Format и проверяет его."""

    def __init__(self, settings: Settings) -> None:
        """Сохраняет конфигурацию подключения к PostgreSQL для создания дампов.

        Args:
            settings: Настройки приложения.
        """
        self.settings = settings

    def create_dump(self, *, backup_dir: Path, stem: str) -> DumpArtifact:
        """Создаёт Custom Format дамп, проверяет его оглавление и рассчитывает SHA-256.

        Дамп создаётся во временном файле с ограниченными правами доступа.
        Пароль передаётся дочернему процессу через окружение, а не аргументы команды.

        Args:
            backup_dir: Каталог временных и итоговых копий.
            stem: Общая часть имени дампа и манифеста.

        Returns:
            Проверенный артефакт с размером и SHA-256.

        Raises:
            DumpCreationError: Если утилиты PostgreSQL отсутствуют, дамп не создан,
                проверка не пройдена или файл не удалось прочитать.
        """
        temporary_dump: Path | None = None
        stage = "locate PostgreSQL utilities"
        dump_created = False
        validation_status = "not_run"
        try:
            pg_dump = shutil.which("pg_dump")
            if pg_dump is None:
                raise DumpCreationError("pg_dump utility was not found")
            pg_restore = shutil.which("pg_restore")
            if pg_restore is None:
                raise DumpCreationError("pg_restore utility was not found")

            stage = "convert DATABASE_URL for PostgreSQL utilities"
            connection = self._connection_info(self.settings.database_url)
            command_env = self._child_environment(connection.password)

            stage = "run pg_dump"
            temporary_dump = self._new_temporary_file(
                backup_dir, f".{stem}.", ".dump.tmp"
            )
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
                raise DumpCreationError(
                    f"pg_dump exited with status {dump_process.returncode}"
                )
            if not temporary_dump.is_file():
                raise DumpCreationError("pg_dump did not create a dump file")
            size_bytes = temporary_dump.stat().st_size
            if size_bytes <= 0:
                raise DumpCreationError("pg_dump created an empty dump file")
            dump_created = True

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
                raise DumpCreationError(
                    "pg_restore --list exited with status "
                    f"{restore_process.returncode}",
                    dump_created=True,
                    validation_status="failed",
                )
            validation_status = "passed"

            stage = "calculate SHA-256"
            sha256 = self._sha256(temporary_dump)
            size_bytes = temporary_dump.stat().st_size
            with temporary_dump.open("rb") as stream:
                os.fsync(stream.fileno())

            artifact = DumpArtifact(
                path=temporary_dump,
                size_bytes=size_bytes,
                sha256=sha256,
            )
            temporary_dump = None
            return artifact
        except DumpCreationError as exc:
            self._cleanup(temporary_dump)
            if exc.dump_created or exc.validation_status != "not_run":
                raise
            raise DumpCreationError(
                str(exc),
                dump_created=dump_created,
                validation_status=validation_status,
            ) from None
        except Exception as exc:  # noqa: BLE001 — normalize unexpected PostgreSQL tool failures
            self._cleanup(temporary_dump)
            logger.error("PostgreSQL dump failed in %s (%s)", stage, type(exc).__name__)
            raise DumpCreationError(
                f"{stage} failed ({type(exc).__name__})",
                dump_created=dump_created,
                validation_status=validation_status,
            ) from None

    @staticmethod
    def _connection_info(database_url: str) -> _ConnectionInfo:
        """Разбирает DATABASE_URL и формирует параметры для утилит PostgreSQL.

        Args:
            database_url: URL подключения SQLAlchemy.

        Returns:
            URI без секрета и пароль отдельно для PGPASSWORD.
        """
        try:
            url = make_url(database_url)
        except Exception:  # noqa: BLE001 — expose only the sanitized URL parsing failure
            raise DumpCreationError("DATABASE_URL is invalid") from None
        if not url.drivername.startswith("postgresql"):
            raise DumpCreationError("DATABASE_URL must use a PostgreSQL driver")

        query = {key.lower(): value for key, value in url.query.items()}
        query_password = query.pop("password", None)
        if any("password" in key for key in query):
            raise DumpCreationError(
                "DATABASE_URL contains an unsupported password parameter"
            )

        ssl = query.pop("ssl", None)
        timeout = query.pop("timeout", None)
        unsupported_options = set(query) - _LIBPQ_QUERY_KEYS
        if unsupported_options:
            raise DumpCreationError(
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
                raise DumpCreationError(
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
        except Exception:  # noqa: BLE001 — expose only the sanitized URL conversion failure
            raise DumpCreationError(
                "DATABASE_URL could not be converted for PostgreSQL utilities"
            ) from None
        password = url.password
        if password is None and query_password is not None:
            password = str(query_password)
        return _ConnectionInfo(database_uri=uri, password=password)

    @staticmethod
    def _child_environment(password: str | None) -> dict[str, str]:
        """Создаёт безопасное окружение дочернего процесса PostgreSQL CLI.

        Args:
            password: Пароль подключения или None.

        Returns:
            Копия окружения с PGPASSWORD, если пароль задан.
        """
        environment = os.environ.copy()
        environment.pop("PGPASSWORD", None)
        if password:
            environment["PGPASSWORD"] = password
        return environment

    @staticmethod
    def _new_temporary_file(directory: Path, prefix: str, suffix: str) -> Path:
        """Создаёт закрытый временный файл в указанном каталоге.

        Args:
            directory: Каталог временного файла.
            prefix: Префикс имени.
            suffix: Расширение файла.

        Returns:
            Путь к созданному временному файлу.
        """
        with tempfile.NamedTemporaryFile(
            prefix=prefix,
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
        """Вычисляет SHA-256 файла потоковым чтением.

        Args:
            path: Путь к файлу.

        Returns:
            Хеш в шестнадцатеричном формате.
        """
        digest = hashlib.sha256()
        with path.open("rb") as dump_file:
            for block in iter(lambda: dump_file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _cleanup(path: Path | None) -> None:
        """Безопасно удаляет временный файл, если путь задан.
        """
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("PostgreSQL temporary dump cleanup failed (%s)", type(exc).__name__)
