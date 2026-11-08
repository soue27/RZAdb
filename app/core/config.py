from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RZAdb"
    debug: bool = False
    database_url: str
    session_secret: str
    document_templates_dir: Path = Path("data/document_templates")

    backup_enabled: bool = False
    backup_local_enabled: bool = True
    backup_local_dir: Path = Path("data/backups")
    backup_local_retention_count: int = Field(default=7, ge=1, le=365)
    backup_email_enabled: bool = False
    backup_email_to: str | None = None
    backup_yandex_disk_enabled: bool = False
    backup_yandex_disk_token: SecretStr | None = None
    backup_yandex_disk_folder: str = "/RZAdb/backups"
    backup_yandex_disk_retention_count: int = Field(default=7, ge=1, le=365)

    # SMTP — email digest
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Feedback
    # Обратная связь
    feedback_email: str | None = None
    app_base_url: str | None = None
    feedback_max_length: int = 5000



@lru_cache
def get_settings() -> Settings:
    return Settings()
