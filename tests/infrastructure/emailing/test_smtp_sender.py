
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "database_url": (
            "postgresql+asyncpg://user:password@localhost:5432/rzadb"
        ),
        "session_secret": "test-secret",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "sender@example.com",
        "smtp_password": "test-password",
        "smtp_from_email": "sender@example.com",
        "smtp_starttls": True,
        "smtp_use_ssl": False,
    }
    values.update(overrides)
    return Settings(**values)



@pytest.mark.asyncio
async def test_send_uses_starttls_and_authentication() -> None:
    sender = SMTPEmailSender(make_settings())

    with (
        patch(
            "app.infrastructure.emailing.smtp_sender.smtplib.SMTP"
        ) as smtp_factory,
        patch(
            "app.infrastructure.emailing.smtp_sender.asyncio.to_thread"
        ) as to_thread,
    ):
        client = smtp_factory.return_value.__enter__.return_value
        to_thread.side_effect = lambda func, *args: func(*args)

        await sender.send(
            to="recipient@example.com",
            subject="Test subject",
            body="Plain text",
            html_body="<p>HTML body</p>",
        )

    smtp_factory.assert_called_once_with(
        "smtp.example.com",
        587,
        timeout=30,
    )
    client.starttls.assert_called_once()
    client.login.assert_called_once_with(
        "sender@example.com",
        "test-password",
    )

    message = client.send_message.call_args.args[0]
    assert message["To"] == "recipient@example.com"
    assert message["Subject"] == "Test subject"
    assert message.get_body(preferencelist=("plain",)).get_content() == (
        "Plain text\n"
    )
    assert message.get_body(preferencelist=("html",)) is not None


def test_sender_rejects_missing_smtp_host() -> None:
    with pytest.raises(ValueError, match="SMTP_HOST"):
        SMTPEmailSender(make_settings(smtp_host=None))


def test_sender_rejects_conflicting_tls_modes() -> None:
    with pytest.raises(ValueError, match="cannot both be enabled"):
        SMTPEmailSender(make_settings(smtp_use_ssl=True))


def test_sender_requires_both_authentication_fields() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        SMTPEmailSender(make_settings(smtp_password=None))
