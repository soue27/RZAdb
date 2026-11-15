from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.enums import UserRole
from app.domain.user import User
from app.infrastructure.database import models  # noqa: F401
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)


async def send_health_notification(payload: dict[str, Any]) -> int:
    """Send one health notice only to the unique active SUPERADMIN."""
    async with async_session_factory() as session:
        recipients = list(
            (
                await session.scalars(
                    select(User.email).where(
                        User.role == UserRole.SUPERADMIN,
                        User.active.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
            ).all()
        )

    if len(recipients) != 1:
        logger.error(
            "Health notification skipped: expected one active SUPERADMIN, found %d",
            len(recipients),
        )
        return 2

    failures = payload.get("failures")
    recoveries = payload.get("recoveries")
    if not isinstance(failures, list) or not isinstance(recoveries, list):
        logger.error("Health notification skipped: invalid payload")
        return 2
    lines = ["Состояние фоновых задач RZAdb", ""]
    if failures:
        lines.extend(["Обнаружены неисправности:", *(f"- {item}" for item in failures)])
    if failures and recoveries:
        lines.append("")
    if recoveries:
        lines.extend(["Восстановлено:", *(f"- {item}" for item in recoveries)])
    try:
        await SMTPEmailSender(get_settings()).send(
            to=recipients[0],
            subject="RZAdb: состояние фоновых задач",
            body="\n".join(lines),
        )
    except Exception as exc:  # noqa: BLE001 — do not mask the originating task error.
        logger.error("Health notification delivery failed (%s)", type(exc).__name__)
        return 1
    logger.info("Health notification delivered to the active SUPERADMIN")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, TypeError):
        logger.error("Health notification skipped: invalid input")
        return 2
    if not isinstance(payload, dict):
        logger.error("Health notification skipped: invalid input")
        return 2
    return asyncio.run(send_health_notification(payload))


if __name__ == "__main__":
    raise SystemExit(main())
