from pathlib import Path

from app.core.config import Settings


def test_smtp_settings_have_safe_defaults() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost:5432/rzadb",
        session_secret="test-secret",
    )

    assert settings.smtp_host is None
    assert settings.smtp_port == 587
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_from_email is None
    assert settings.smtp_starttls is True
    assert settings.smtp_use_ssl is False
    assert str(settings.document_templates_dir) == "data/document_templates"


def test_document_templates_directory_can_be_configured() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost:5432/rzadb",
        session_secret="test-secret",
        document_templates_dir="/opt/rzadb/templates",
    )

    assert str(settings.document_templates_dir) == "/opt/rzadb/templates"


def test_backup_settings_have_safe_local_defaults() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost:5432/rzadb",
        session_secret="test-secret",
    )

    assert settings.backup_enabled is False
    assert settings.backup_local_enabled is True
    assert settings.backup_local_dir == Path("data/backups")
    assert settings.backup_local_retention_count == 7


def test_smtp_settings_can_be_configured() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost:5432/rzadb",
        session_secret="test-secret",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="smtp-test-password",
        smtp_from_email="sender@example.com",
        smtp_starttls=True,
        smtp_use_ssl=False,
    )

    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 587
    assert settings.smtp_username == "sender@example.com"
    assert settings.smtp_password == "smtp-test-password"
    assert settings.smtp_from_email == "sender@example.com"
    assert settings.smtp_starttls is True
    assert settings.smtp_use_ssl is False
