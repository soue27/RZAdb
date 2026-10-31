
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

logger = logging.getLogger(__name__)

EKATERINBURG_TZ = ZoneInfo("Asia/Yekaterinburg")


class FeedbackService:
    """Отправляет сообщения пользователей администрации приложения."""

    def __init__(
        self,
        *,
        sender: SMTPEmailSender,
        recipient: str,
        app_base_url: str | None = None,
    ) -> None:
        self.sender = sender
        self.recipient = recipient
        self.app_base_url = app_base_url

    async def send(
        self,
        *,
        user_id: str,
        full_name: str,
        email: str,
        role: str,
        enterprise_name: str | None,
        message: str,
    ) -> None:
        submitted_at = datetime.now(EKATERINBURG_TZ)

        text_body = "\n".join(
            [
                "Новое сообщение обратной связи RZAdb",
                "",
                f"Дата и время: {submitted_at:%d.%m.%Y %H:%M:%S}",
                "",
                "Данные пользователя:",
                f"ФИО: {full_name}",
                f"Email: {email}",
                f"Роль: {role}",
                f"Предприятие: {enterprise_name or 'Не указано'}",
                f"ID пользователя: {user_id}",
                "",
                "Сообщение:",
                message,
                "",
                f"Приложение: {self.app_base_url or 'Не указано'}",
            ]
        )

        await self.sender.send(
            to=self.recipient,
            subject=f"Обратная связь RZAdb — {full_name}",
            body=text_body,
        )
