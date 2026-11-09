from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.infrastructure.backup.coordinator import (
    BackupCoordinator,
    BackupError,
)
from app.infrastructure.backup.run_lock import BackupAlreadyRunning, BackupRunLock


async def run() -> int:
    """Выполняет один CLI-запуск резервного копирования PostgreSQL.

    Получает настройки, захватывает общий lock и запускает BackupCoordinator.
    Возвращает код завершения, соответствующий итоговому статусу каналов.

    Returns:
        0 при полном успехе, 2 при частичном успехе, 1 при ошибке или занятом lock.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    try:
        with BackupRunLock(settings.backup_local_dir):
            result = await BackupCoordinator(settings).run()
    except BackupAlreadyRunning:
        logging.error("Another PostgreSQL backup is already running")
        return 1
    except BackupError as exc:
        logging.error("Database backup failed: %s", exc)
        return 1
    print(f"Backup run {result['run_id']}: {result['status']}")
    print(f"Manifest: {result['manifest_path']}")
    return {"success": 0, "partial_success": 2, "failed": 1}[result["status"]]


def main() -> int:
    """Точка входа CLI: запускает асинхронный сценарий резервного копирования.

    Returns:
        Код завершения, возвращённый run().
    """
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
