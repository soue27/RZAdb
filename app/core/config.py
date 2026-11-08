from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RZAdb"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
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
    error_email_to: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return normalized

    @field_validator("error_email_to", mode="before")
    @classmethod
    def normalize_error_email_to(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    # Feedback
    # Обратная связь
    feedback_email: str | None = None
    app_base_url: str | None = None
    feedback_max_length: int = 5000



@lru_cache
def get_settings() -> Settings:
    return Settings()
