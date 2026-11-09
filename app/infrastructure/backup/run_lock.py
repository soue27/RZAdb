from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Self


class BackupAlreadyRunning(RuntimeError):
    """Другой процесс уже удерживает блокировку резервного копирования PostgreSQL."""


class BackupRunLock:
    """Межпроцессная advisory-блокировка, общая для CLI и веб-интерфейса."""

    def __init__(self, backup_dir: Path) -> None:
        """Формирует путь lock-файла в каталоге резервных копий.

        Args:
            backup_dir: Каталог резервных копий.
        """
        self.path = backup_dir / ".backup-run.lock"
        self._descriptor: int | None = None

    def acquire(self) -> BackupRunLock:
        """Создаёт lock-файл с ограниченными правами и захватывает неблокирующую блокировку.

        Returns:
            Текущий экземпляр блокировки.

        Raises:
            BackupAlreadyRunning: Если другой процесс уже выполняет резервирование.
        """
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise BackupAlreadyRunning from None
        self._descriptor = descriptor
        return self

    def release(self) -> None:
        """Освобождает advisory-блокировку и закрывает файловый дескриптор.
        """
        if self._descriptor is None:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._descriptor = None

    def __enter__(self) -> Self:
        """Захватывает блокировку при входе в контекстный менеджер.

        Returns:
            Текущий экземпляр блокировки.
        """
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        """Освобождает блокировку при выходе из контекстного менеджера.
        """
        self.release()
