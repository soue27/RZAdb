from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.infrastructure.backup.service import BackupError, LocalPostgresBackupService


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = LocalPostgresBackupService(get_settings()).create_backup()
    except BackupError as exc:
        logging.error("Database backup failed: %s", exc)
        return 1
    print(
        f"Backup saved: {result.dump_path} "
        f"(sha256={result.sha256}, manifest={result.manifest_path})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
