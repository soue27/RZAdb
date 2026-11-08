from __future__ import annotations

import fcntl
import os
from pathlib import Path


class BackupAlreadyRunning(RuntimeError):
    """Another process currently owns the PostgreSQL backup lock."""


class BackupRunLock:
    """A process-wide advisory lock shared by the CLI and web interface."""

    def __init__(self, backup_dir: Path) -> None:
        self.path = backup_dir / ".backup-run.lock"
        self._descriptor: int | None = None

    def acquire(self) -> BackupRunLock:
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
        if self._descriptor is None:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._descriptor = None

    def __enter__(self) -> BackupRunLock:
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()
