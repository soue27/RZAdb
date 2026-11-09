from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.infrastructure.backup.dump import DumpArtifact
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)

_DUMP_NAME_PATTERN = re.compile(
    r"^rzadb_\d{8}T\d{12}Z_[0-9a-f]{32}\.dump$"
)
_YANDEX_API = "https://cloud-api.yandex.net/v1/disk/resources"
_CHUNK_SIZE = 1024 * 1024


class ChannelConfigurationError(ValueError):
    """Включённый канал резервного копирования не имеет обязательных настроек."""


@dataclass(frozen=True)
class ChannelResult:
    """Результат работы одного канала резервного копирования и его ротации.
    """
    status: str
    error: str | None = None
    path: str | None = None
    retention_status: str | None = None
    retention_error: str | None = None

    def to_dict(self, *, enabled: bool = True) -> dict[str, Any]:
        """Преобразует результат канала в сериализуемый словарь манифеста.

        Args:
            enabled: Был ли канал включён в конфигурации.

        Returns:
            Словарь статуса, ошибки, пути и результата ротации.
        """
        return {
            "enabled": enabled,
            "status": self.status,
            "error": self.error,
            "path": self.path,
            "retention_status": self.retention_status,
            "retention_error": self.retention_error,
        }


class LocalBackupChannel:
    """Атомарно публикует проверенный дамп и сохраняет заданное число успешных локальных копий."""

    def __init__(self, settings: Settings) -> None:
        """Сохраняет каталог локальных копий и лимит хранения.

        Args:
            settings: Настройки резервного копирования.
        """
        self.backup_dir = settings.backup_local_dir
        self.retention_count = settings.backup_local_retention_count

    def publish(self, artifact: DumpArtifact, dump_name: str) -> Path:
        """Атомарно перемещает проверенный временный дамп в локальный каталог копий.

        Args:
            artifact: Проверенный артефакт дампа.
            dump_name: Имя итогового файла.

        Returns:
            Путь к опубликованному дампу.
        """
        target = self.backup_dir / dump_name
        os.replace(artifact.path, target)
        return target

    def apply_retention(self) -> None:
        """Удаляет старые успешные локальные пары дамп/манифест с учётом лимита хранения.
        """
        successful: list[tuple[str, Path, Path]] = []
        for manifest_path in self.backup_dir.glob("rzadb_*.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                dump_name = manifest.get("dump_filename")
                if not isinstance(dump_name, str) or not _DUMP_NAME_PATTERN.fullmatch(
                    dump_name
                ):
                    continue
                dump_path = self.backup_dir / dump_name
                new_channel_state = manifest.get("channels", {}).get("local", {})
                local_state = manifest.get("local_storage", {})
                local_succeeded = (
                    new_channel_state.get("status") == "success"
                    or local_state.get("status") == "success"
                )
                if (
                    not local_succeeded
                    or manifest.get("dump_created") is not True
                    or manifest.get("pg_restore_list_validation") != "passed"
                    or dump_path.parent != self.backup_dir
                    or not dump_path.is_file()
                ):
                    continue
                successful.append(
                    (str(manifest.get("started_at", "")), dump_path, manifest_path)
                )
            except (OSError, ValueError, TypeError, AttributeError):
                continue

        successful.sort(key=lambda item: item[0], reverse=True)
        for _, dump_path, manifest_path in successful[self.retention_count :]:
            try:
                dump_path.unlink()
                manifest_path.unlink()
            except OSError as exc:
                logger.warning(
                    "Local backup retention could not remove a pair (%s)",
                    type(exc).__name__,
                )


class EmailBackupChannel:
    """Отправляет проверенный дамп вложением на настроенный email-адрес.
    """
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.recipient = settings.backup_email_to
        self.sender: SMTPEmailSender | None = None

    def validate(self) -> None:
        """Проверяет обязательные настройки email-канала до начала резервирования.

        Raises:
            ChannelConfigurationError: Если включённый канал не настроен.
        """
        if not self.recipient:
            raise ChannelConfigurationError("BACKUP_EMAIL_TO is not configured")
        if self.recipient.strip() != self.recipient or "@" not in self.recipient:
            raise ChannelConfigurationError("BACKUP_EMAIL_TO is invalid")
        self.sender = SMTPEmailSender(self.settings)

    async def send(
        self,
        *,
        dump_path: Path,
        run_id: str,
        started_at: str,
        size_bytes: int,
        sha256: str,
        dump_name: str,
    ) -> ChannelResult:
        """Отправляет дамп как вложение письма.

        Args:
            dump_path: Путь к файлу дампа.
            dump_name: Имя вложения.

        Returns:
            Результат отправки канала.
        """
        if self.sender is None:
            self.validate()
        assert self.sender is not None
        subject = f"RZAdb PostgreSQL backup — {started_at}"
        body = (
            "PostgreSQL backup was created.\n\n"
            f"Run ID: {run_id}\n"
            f"Created at (UTC): {started_at}\n"
            f"Size: {size_bytes} bytes\n"
            f"SHA-256: {sha256}\n"
        )
        await self.sender.send(
            to=self.recipient,
            subject=subject,
            body=body,
            attachments=(dump_path,),
            attachment_name=dump_name,
        )
        return ChannelResult(status="success", path=dump_name)


class YandexDiskBackupChannel:
    """Загружает дампы на Яндекс Диск и выполняет ротацию удалённых копий.
    """
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token = settings.backup_yandex_disk_token
        self.folder = settings.backup_yandex_disk_folder.rstrip("/")
        self.retention_count = settings.backup_yandex_disk_retention_count

    def validate(self) -> None:
        """Проверяет обязательные настройки Яндекс Диска.

        Raises:
            ChannelConfigurationError: Если включённый канал не настроен.
        """
        if self.token is None or not self.token.get_secret_value():
            raise ChannelConfigurationError(
                "BACKUP_YANDEX_DISK_TOKEN is not configured"
            )
        if not self.folder.startswith("/") or ".." in self.folder.split("/"):
            raise ChannelConfigurationError(
                "BACKUP_YANDEX_DISK_FOLDER must be an absolute Disk path"
            )

    def upload(self, dump_path: Path, dump_name: str) -> ChannelResult:
        """Загружает дамп на Яндекс Диск и применяет retention после подтверждения загрузки.

        Args:
            dump_path: Путь к дампу.
            dump_name: Имя файла на диске.

        Returns:
            Результат загрузки и очистки старых копий.
        """
        self.validate()
        assert self.token is not None
        headers = {"Authorization": f"OAuth {self.token.get_secret_value()}"}
        remote_path = f"{self.folder}/{dump_name}"
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=120.0, pool=20.0)
        with httpx.Client(timeout=timeout) as client:
            self._ensure_folder(client, headers)
            upload_response = client.get(
                f"{_YANDEX_API}/upload",
                params={"path": remote_path},
                headers=headers,
            )
            upload_response.raise_for_status()
            upload_url = upload_response.json().get("href")
            if not isinstance(upload_url, str) or not upload_url:
                raise RuntimeError("Yandex Disk did not return an upload URL")
            parsed_upload_url = urlparse(upload_url)
            if parsed_upload_url.scheme != "https" or not parsed_upload_url.netloc:
                raise RuntimeError("Yandex Disk returned an invalid upload URL")

            with dump_path.open("rb") as dump_file:
                upload_result = client.put(
                    upload_url,
                    content=self._file_chunks(dump_file),
                    headers={"Content-Type": "application/octet-stream"},
                )
            upload_result.raise_for_status()

            retention_status = "success"
            retention_error = None
            try:
                self._apply_retention(client, headers, dump_name)
            except Exception as exc:
                retention_status = "failed"
                retention_error = f"Yandex Disk retention failed ({type(exc).__name__})"
                logger.warning(
                    "Yandex Disk upload succeeded but retention failed (%s)",
                    type(exc).__name__,
                )

        return ChannelResult(
            status="success",
            path=remote_path,
            retention_status=retention_status,
            retention_error=retention_error,
        )

    def _ensure_folder(self, client: httpx.Client, headers: dict[str, str]) -> None:
        """Создаёт каталог резервных копий на Яндекс Диске, если его ещё нет.
        """
        current = ""
        for segment in (item for item in self.folder.split("/") if item):
            current += f"/{segment}"
            response = client.get(
                _YANDEX_API,
                params={"path": current},
                headers=headers,
            )
            if response.status_code == 200:
                continue
            if response.status_code != 404:
                response.raise_for_status()
            create_response = client.put(
                _YANDEX_API,
                params={"path": current},
                headers=headers,
            )
            if create_response.status_code == 409:
                continue
            create_response.raise_for_status()

    def _apply_retention(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        current_dump_name: str,
    ) -> None:
        """Удаляет устаревшие резервные копии на Яндекс Диске после успешной загрузки.
        """
        files = self._list_backup_files(client, headers)
        if not any(item["name"] == current_dump_name for item in files):
            files.append({"name": current_dump_name})
        files.sort(key=lambda item: item["name"], reverse=True)
        for item in files[self.retention_count :]:
            response = client.delete(
                _YANDEX_API,
                params={
                    "path": f"{self.folder}/{item['name']}",
                    "permanently": "true",
                },
                headers=headers,
            )
            response.raise_for_status()

    def _list_backup_files(
        self,
        client: httpx.Client,
        headers: dict[str, str],
    ) -> list[dict[str, str]]:
        """Получает список файлов резервных копий в удалённом каталоге.
        """
        files: list[dict[str, str]] = []
        offset = 0
        while True:
            response = client.get(
                _YANDEX_API,
                params={
                    "path": self.folder,
                    "limit": 1000,
                    "offset": offset,
                    "fields": "_embedded.items.name,_embedded.items.type,_embedded.total",
                },
                headers=headers,
            )
            response.raise_for_status()
            embedded = response.json().get("_embedded", {})
            page = embedded.get("items", [])
            for item in page:
                name = item.get("name")
                if (
                    item.get("type") == "file"
                    and isinstance(name, str)
                    and _DUMP_NAME_PATTERN.fullmatch(name)
                ):
                    files.append({"name": name})
            offset += len(page)
            total = embedded.get("total", offset)
            if not page or offset >= total:
                return files

    @staticmethod
    def _file_chunks(dump_file):
        """Последовательно читает файл блоками для потоковой загрузки.

        Args:
            dump_file: Открытый бинарный файл.

        Yields:
            Блоки бинарных данных фиксированного размера.
        """
        while block := dump_file.read(_CHUNK_SIZE):
            yield block
