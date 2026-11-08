from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.infrastructure.backup.coordinator import (
    BackupCoordinator,
    BackupError,
)


async def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = await BackupCoordinator(get_settings()).run()
    except BackupError as exc:
        logging.error("Database backup failed: %s", exc)
        return 1
    print(f"Backup run {result['run_id']}: {result['status']}")
    print(f"Manifest: {result['manifest_path']}")
    return {"success": 0, "partial_success": 2, "failed": 1}[result["status"]]


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
