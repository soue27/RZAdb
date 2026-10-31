from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RZAdb"
    debug: bool = False
    database_url: str
    session_secret: str

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