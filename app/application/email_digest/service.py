from dataclasses import dataclass
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from app.application.email_digest.formatter import (
    DigestTask,
    EmailDigestFormatter,
)
from app.application.tasks.repository import TaskRepository
from app.application.users.repository import UserRepository
from app.core.config import Settings
from app.domain.enums import UserRole
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)

EKATERINBURG_TZ = ZoneInfo("Asia/Yekaterinburg")


@dataclass(frozen=True, slots=True)
class DigestRunResult:
    """Итоги одного запуска рассылки."""

    recipients: int = 0
    sent: int = 0
    skipped_empty: int = 0
    skipped_no_enterprise: int = 0
    failed: int = 0


class EmailDigestService:
    """Собирает и отправляет персональные сводки задач."""

    def __init__(
        self,
        *,
        user_repository: UserRepository,
        task_repository: TaskRepository,
        formatter: EmailDigestFormatter,
        sender: SMTPEmailSender,
    ) -> None:
        self.user_repository = user_repository
        self.task_repository = task_repository
        self.formatter = formatter
        self.sender = sender

    async def send_digests(
        self,
        *,
        now: datetime | None = None,
    ) -> DigestRunResult:
        """Отправляет сводки активным инженерам и руководителям."""
        current_time = now or datetime.now(EKATERINBURG_TZ)

        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        recipients = await self.user_repository.list_active_email_digest_recipients()

        sent = 0
        skipped_empty = 0
        skipped_no_enterprise = 0
        failed = 0

        for recipient in recipients:
            try:
                if recipient.role == UserRole.ENGINEER:
                    tasks = await self.task_repository.list_for_email_digest_engineer(
                        recipient.id
                    )
                elif recipient.role == UserRole.MANAGER:
                    if recipient.enterprise_id is None:
                        skipped_no_enterprise += 1
                        logger.warning(
                            "Email digest skipped: manager %s has no enterprise",
                            recipient.id,
                        )
                        continue

                    tasks = await self.task_repository.list_for_email_digest_manager(
                        recipient.enterprise_id
                    )
                else:
                    # Репозиторий уже фильтрует роли; дополнительная
                    # проверка защищает от некорректных данных.
                    continue

                if not tasks:
                    skipped_empty += 1
                    continue

                digest_tasks = [
                    DigestTask(
                        description=task.description or "",
                        status=task.status.value,
                        deadline_at=task.deadline_at,
                        assigned_to=task.assigned_to,
                        assignee_name=(
                            task.assigned_to_user.full_name
                            if task.assigned_to_user is not None
                            else None
                        ),
                    )
                    for task in tasks
                ]

                if recipient.role == UserRole.ENGINEER:
                    message = self.formatter.format_engineer_digest(
                        recipient_name=recipient.full_name,
                        recipient_id=recipient.id,
                        tasks=digest_tasks,
                        now=current_time,
                    )
                else:
                    message = self.formatter.format_manager_digest(
                        recipient_name=recipient.full_name,
                        recipient_id=recipient.id,
                        tasks=digest_tasks,
                        now=current_time,
                    )

                await self.sender.send(
                    to=recipient.email,
                    subject=message.subject,
                    body=message.text_body,
                    html_body=message.html_body,
                )
                sent += 1

            except Exception:
                failed += 1
                logger.exception(
                    "Email digest delivery failed for user %s",
                    recipient.id,
                )

        return DigestRunResult(
            recipients=len(recipients),
            sent=sent,
            skipped_empty=skipped_empty,
            skipped_no_enterprise=skipped_no_enterprise,
            failed=failed,
        )
