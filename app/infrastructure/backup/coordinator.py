from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.core.config import Settings
from app.infrastructure.backup.channels import (
    ChannelConfigurationError,
    ChannelResult,
    EmailBackupChannel,
    LocalBackupChannel,
    YandexDiskBackupChannel,
)
from app.infrastructure.backup.dump import (
    DumpArtifact,
    DumpCreationError,
    PostgresDumpService,
)

logger = logging.getLogger(__name__)


class BackupError(RuntimeError):
    """Базовая ошибка незавершённого запуска резервного копирования."""


class BackupDisabledError(BackupError):
    """Резервное копирование отключено общим переключателем настроек."""


class BackupManifestError(BackupError):
    """Итоговый манифест запуска не удалось надёжно записать на диск."""


class BackupCoordinator:
    """Координирует создание дампа, независимые каналы хранения и итоговый манифест запуска.
    """
    def __init__(self, settings: Settings) -> None:
        """Создаёт сервис дампа и адаптеры всех каналов резервного копирования.

        Args:
            settings: Настройки БД, каталогов и каналов резервирования.
        """
        self.settings = settings
        self.dump_service = PostgresDumpService(settings)
        self.local_channel = LocalBackupChannel(settings)
        self.email_channel = EmailBackupChannel(settings)
        self.yandex_disk_channel = YandexDiskBackupChannel(settings)

    async def run(self) -> dict[str, Any]:
        """Выполняет полный цикл резервного копирования PostgreSQL.

        Создаёт и проверяет дамп, последовательно обрабатывает включённые каналы,
        сохраняет результат каждого канала и общий статус в манифесте. Ошибка одного
        канала не отменяет остальные.

        Returns:
            Итоговый манифест запуска с run_id, статусами каналов и путём к файлу.

        Raises:
            BackupDisabledError: Если резервирование отключено.
            BackupError: Если создание дампа не удалось.
            BackupManifestError: Если итоговый манифест не удалось записать.
        """
        if not self.settings.backup_enabled:
            raise BackupDisabledError("Database backup is disabled")

        backup_dir = self.settings.backup_local_dir
        run_id = uuid4()
        started_at = datetime.now(UTC)
        started_clock = time.monotonic()
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"rzadb_{timestamp}_{run_id.hex}"
        dump_name = f"{stem}.dump"
        manifest_path = backup_dir / f"{stem}.json"
        artifact: DumpArtifact | None = None

        manifest: dict[str, Any] = {
            "run_id": str(run_id),
            "started_at": started_at.isoformat(),
            "dump_filename": dump_name,
            "dump_created": False,
            "pg_restore_list_validation": "not_run",
            "size_bytes": None,
            "sha256": None,
            "duration_seconds": 0.0,
            "channels": {
                "local": self._channel_pending(self.settings.backup_local_enabled),
                "email": self._channel_pending(self.settings.backup_email_enabled),
                "yandex_disk": self._channel_pending(
                    self.settings.backup_yandex_disk_enabled
                ),
            },
            "local_storage": {
                "enabled": self.settings.backup_local_enabled,
                "status": "disabled"
                if not self.settings.backup_local_enabled
                else "pending",
            },
            "status": "running",
            "error": None,
        }

        try:
            try:
                backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(backup_dir, 0o700)
            except Exception as exc:  # noqa: BLE001 — preserve a manifest for any filesystem failure
                self._manifest_write_error(run_id, exc)

            channel_ready = self._validate_enabled_channels(manifest)
            if not any(channel_ready.values()):
                manifest["error"] = "No enabled backup channel is ready"
                manifest["status"] = "failed"
                return await self._save_manifest_and_result(
                    manifest,
                    manifest_path,
                    backup_dir,
                    run_id,
                    started_clock,
                    artifact,
                )

            try:
                artifact = self.dump_service.create_dump(
                    backup_dir=backup_dir,
                    stem=stem,
                )
            except DumpCreationError as exc:
                manifest["error"] = str(exc)
                manifest["dump_created"] = exc.dump_created
                manifest["pg_restore_list_validation"] = exc.validation_status
                for name, ready in channel_ready.items():
                    if ready:
                        outcome = manifest["channels"][name]
                        outcome["status"] = "not_attempted"
                        outcome["error"] = "Dump creation or validation failed"
                manifest["status"] = "failed"
                return await self._save_manifest_and_result(
                    manifest,
                    manifest_path,
                    backup_dir,
                    run_id,
                    started_clock,
                    artifact,
                )

            manifest["dump_created"] = True
            manifest["pg_restore_list_validation"] = "passed"
            manifest["size_bytes"] = artifact.size_bytes
            manifest["sha256"] = artifact.sha256

            delivery_path = artifact.path
            if channel_ready.get("local"):
                try:
                    local_path = self.local_channel.publish(artifact, dump_name)
                    delivery_path = local_path
                    self._set_channel_result(
                        manifest, "local", ChannelResult("success", path=dump_name)
                    )
                except Exception as exc:  # noqa: BLE001 — channel failures must not stop other channels
                    self._set_channel_failure(manifest, "local", exc)
            self._sync_legacy_local_status(manifest)

            if channel_ready.get("email"):
                try:
                    result = await self.email_channel.send(
                        dump_path=delivery_path,
                        run_id=str(run_id),
                        started_at=started_at.isoformat(),
                        size_bytes=artifact.size_bytes,
                        sha256=artifact.sha256,
                        dump_name=dump_name,
                    )
                    self._set_channel_result(manifest, "email", result)
                except Exception as exc:  # noqa: BLE001 — channel failures must not stop other channels
                    self._set_channel_failure(manifest, "email", exc)

            if channel_ready.get("yandex_disk"):
                try:
                    result = self.yandex_disk_channel.upload(delivery_path, dump_name)
                    self._set_channel_result(manifest, "yandex_disk", result)
                except Exception as exc:  # noqa: BLE001 — channel failures must not stop other channels
                    self._set_channel_failure(manifest, "yandex_disk", exc)

            self._sync_legacy_local_status(manifest)
            manifest["status"] = self._overall_status(manifest)
            return await self._save_manifest_and_result(
                manifest,
                manifest_path,
                backup_dir,
                run_id,
                started_clock,
                artifact,
            )
        finally:
            if artifact is not None:
                try:
                    artifact.cleanup()
                except OSError as exc:
                    logger.warning(
                        "Backup run %s temporary dump cleanup failed (%s)",
                        run_id,
                        type(exc).__name__,
                    )

    def _validate_enabled_channels(self, manifest: dict[str, Any]) -> dict[str, bool]:
        """Проверяет конфигурацию всех включённых каналов и возвращает их состояние.

        Args:
            manifest: Текущий манифест запуска.

        Returns:
            Словарь признаков включения локального, email- и Yandex Disk-каналов.
        """
        readiness = {
            "local": self.settings.backup_local_enabled,
            "email": self.settings.backup_email_enabled,
            "yandex_disk": self.settings.backup_yandex_disk_enabled,
        }
        validators = {
            "email": self.email_channel.validate,
            "yandex_disk": self.yandex_disk_channel.validate,
        }
        for name, validate in validators.items():
            if not readiness[name]:
                continue
            try:
                validate()
            except Exception as exc:  # noqa: BLE001 — channel validation failure is reported per channel
                readiness[name] = False
                self._set_channel_failure(manifest, name, exc)
        return readiness

    async def _save_manifest_and_result(
        self,
        manifest: dict[str, Any],
        manifest_path: Path,
        backup_dir: Path,
        run_id: UUID,
        started_clock: float,
        artifact: DumpArtifact | None,
    ) -> dict[str, Any]:
        """Атомарно сохраняет манифест и формирует итоговый результат запуска.
        """
        manifest["duration_seconds"] = round(time.monotonic() - started_clock, 6)
        self._sync_legacy_local_status(manifest)
        try:
            self._write_manifest_atomic(manifest_path, manifest)
        except Exception as exc:  # noqa: BLE001 — manifest write failures become a backup result
            self._manifest_write_error(run_id, exc)

        if manifest["channels"]["local"]["status"] == "success":
            try:
                self.local_channel.apply_retention()
                manifest["channels"]["local"]["retention_status"] = "success"
            except Exception as exc:  # noqa: BLE001 — retention must not invalidate a saved backup
                manifest["channels"]["local"].update(
                    {
                        "retention_status": "failed",
                        "retention_error": (
                            f"Local retention failed ({type(exc).__name__})"
                        ),
                    }
                )
                logger.warning(
                    "Backup run %s local retention failed (%s)",
                    run_id,
                    type(exc).__name__,
                )
            manifest["status"] = self._overall_status(manifest)
            try:
                self._write_manifest_atomic(manifest_path, manifest)
            except Exception as exc:  # noqa: BLE001 — manifest write failures become a backup result
                self._manifest_write_error(run_id, exc)

        return {
            "run_id": str(run_id),
            "status": manifest["status"],
            "started_at": manifest["started_at"],
            "duration_seconds": manifest["duration_seconds"],
            "dump_path": str(backup_dir / manifest["dump_filename"])
            if manifest["channels"]["local"]["status"] == "success"
            else None,
            "manifest_path": str(manifest_path),
            "error": manifest["error"],
            "size_bytes": artifact.size_bytes if artifact else manifest["size_bytes"],
            "sha256": artifact.sha256 if artifact else manifest["sha256"],
            "channels": manifest["channels"],
        }

    @staticmethod
    def _channel_pending(enabled: bool) -> dict[str, Any]:
        """Создаёт начальное состояние канала до начала его обработки.

        Args:
            enabled: Включён ли канал.

        Returns:
            Словарь начального статуса канала.
        """
        return {
            "enabled": enabled,
            "status": "pending" if enabled else "disabled",
            "error": None,
            "path": None,
            "retention_status": None,
            "retention_error": None,
        }

    @staticmethod
    def _set_channel_result(
        manifest: dict[str, Any], name: str, result: ChannelResult
    ) -> None:
        """Записывает результат выполнения канала в манифест.
        """
        manifest["channels"][name].update(result.to_dict())

    @classmethod
    def _set_channel_failure(
        cls,
        manifest: dict[str, Any],
        name: str,
        error: Exception,
    ) -> None:
        """Записывает ошибку канала, не прерывая обработку остальных каналов.
        """
        if isinstance(error, ChannelConfigurationError) or (
            isinstance(error, ValueError) and name == "email"
        ):
            safe_error = str(error)
        elif isinstance(error, httpx.HTTPStatusError):
            safe_error = f"HTTP request failed with status {error.response.status_code}"
        else:
            safe_error = f"{name} channel failed ({type(error).__name__})"
        manifest["channels"][name].update(
            {"status": "failed", "error": safe_error}
        )
        logger.error(
            "Backup channel %s failed (%s)", name, type(error).__name__
        )

    @staticmethod
    def _sync_legacy_local_status(manifest: dict[str, Any]) -> None:
        """Синхронизирует устаревшие поля локального статуса для совместимости манифеста.
        """
        local = manifest["channels"]["local"]
        manifest["local_storage"] = {
            "enabled": local["enabled"],
            "status": local["status"],
        }

    @staticmethod
    def _overall_status(manifest: dict[str, Any]) -> str:
        """Вычисляет общий статус запуска по результатам включённых каналов.

        Returns:
            success, partial_success или failed.
        """
        enabled = [
            channel
            for channel in manifest["channels"].values()
            if channel["enabled"]
        ]
        successes = sum(channel["status"] == "success" for channel in enabled)
        failures = sum(channel["status"] == "failed" for channel in enabled)
        retention_failures = sum(
            channel.get("retention_status") == "failed" for channel in enabled
        )
        if successes == len(enabled) and not retention_failures:
            return "success"
        if successes:
            return "partial_success"
        if failures or enabled:
            return "failed"
        return "failed"

    @staticmethod
    def _write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
        """Записывает JSON-манифест через временный файл и атомарную замену.
        """
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{path.stem}.",
                suffix=".json.tmp",
                dir=path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                os.chmod(temporary_path, 0o600)
                json.dump(manifest, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            os.chmod(path, 0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _manifest_write_error(run_id: UUID, error: Exception) -> None:
        """Логирует ошибку сохранения манифеста с идентификатором запуска.
        """
        logger.error(
            "Backup run %s manifest write failed (%s)",
            run_id,
            type(error).__name__,
        )
        raise BackupManifestError(
            f"Backup manifest write failed ({type(error).__name__}); run_id={run_id}"
        ) from None
