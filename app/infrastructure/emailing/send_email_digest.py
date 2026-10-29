
import asyncio
import logging

from app.application.email_digest.formatter import EmailDigestFormatter
from app.application.email_digest.service import (
    DigestRunResult,
    EmailDigestService,
)
from app.application.tasks.repository import TaskRepository
from app.application.users.repository import UserRepository
from app.core.config import get_settings
from app.infrastructure.database import models  # noqa: F401
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)


async def run_email_digest() -> DigestRunResult:
    """Выполняет один запуск рассылки email-сводок."""
    settings = get_settings()
    sender = SMTPEmailSender(settings)

    async with async_session_factory() as session:
        service = EmailDigestService(
            user_repository=UserRepository(session),
            task_repository=TaskRepository(session),
            formatter=EmailDigestFormatter(),
            sender=sender,
        )
        result = await service.send_digests()

    logger.info(
        (
            "Email digest run completed: recipients=%s, sent=%s, "
            "skipped_empty=%s, skipped_no_enterprise=%s, failed=%s"
        ),
        result.recipients,
        result.sent,
        result.skipped_empty,
        result.skipped_no_enterprise,
        result.failed,
    )

    return result


def main() -> None:
    """Точка входа CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        result = asyncio.run(run_email_digest())
    except Exception:
        logger.exception("Email digest run failed")
        raise SystemExit(1) from None

    if result.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
