
import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings


class SMTPEmailSender:
    """Отправка email через SMTP без блокировки event loop."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        if not settings.smtp_host:
            raise ValueError("SMTP_HOST is not configured")

        if not settings.smtp_from_email:
            raise ValueError("SMTP_FROM_EMAIL is not configured")

        if settings.smtp_starttls and settings.smtp_use_ssl:
            raise ValueError(
                "SMTP_STARTTLS and SMTP_USE_SSL cannot both be enabled"
            )

        if bool(settings.smtp_username) != bool(settings.smtp_password):
            raise ValueError(
                "SMTP_USERNAME and SMTP_PASSWORD must be configured together"
            )

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> None:
        """Отправляет письмо; SMTP-вызовы выполняются в отдельном потоке."""
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        if html_body is not None:
            message.add_alternative(html_body, subtype="html")

        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        host = self.settings.smtp_host
        port = self.settings.smtp_port

        if self.settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                host,
                port,
                timeout=30,
                context=ssl.create_default_context(),
            ) as client:
                self._deliver(client, message)
            return

        with smtplib.SMTP(host, port, timeout=30) as client:
            if self.settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())

            self._deliver(client, message)

    def _deliver(
        self,
        client: smtplib.SMTP | smtplib.SMTP_SSL,
        message: EmailMessage,
    ) -> None:
        if self.settings.smtp_username:
            client.login(
                self.settings.smtp_username,
                self.settings.smtp_password,
            )

        client.send_message(message)
