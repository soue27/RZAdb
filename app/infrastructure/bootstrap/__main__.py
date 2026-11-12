"""Интерактивная точка входа: python -m app.infrastructure.bootstrap."""

import asyncio
from getpass import getpass

from sqlalchemy.engine import make_url

from app.application.auth.password import PasswordService
from app.application.users.bootstrap import (
    BootstrapCredentials,
    BootstrapError,
    bootstrap_superadmin,
)
from app.core.config import get_settings
from app.infrastructure.database.engine import async_session_factory, engine


def _target_database_display(database_url: str) -> tuple[str, str]:
    url = make_url(database_url)
    if not url.database:
        raise ValueError("database name is missing")
    database_name = url.database
    location = url.host or "локальный Unix socket"
    if url.port is not None:
        location = f"{location}:{url.port}"
    return database_name, f"{location}/{database_name}"


def _request_credentials() -> BootstrapCredentials:
    return BootstrapCredentials(
        full_name=input("ФИО: ").strip(),
        email=input("Email: ").strip(),
        password=getpass("Временный пароль: "),
        password_confirmation=getpass("Повторите временный пароль: "),
    )


async def _run() -> None:
    # SQLAlchemy echo can include bound values; keep credentials out of logs.
    engine.echo = False
    try:
        async with async_session_factory() as session:
            user = await bootstrap_superadmin(
                session,
                _request_credentials,
                PasswordService(),
            )
        print(
            f"SUPERADMIN создан: {user.email}. "
            "При первом входе потребуется сменить пароль."
        )
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    try:
        database_name, location = _target_database_display(settings.database_url)
    except Exception:
        print("Не удалось безопасно определить целевую базу данных.")
        raise SystemExit(1) from None

    print(f"Целевая база данных: {location}")
    confirmation = input(f"Для продолжения введите имя базы данных '{database_name}': ")
    if confirmation != database_name:
        print("Имя базы данных не подтверждено. Bootstrap не выполнен.")
        raise SystemExit(1)

    try:
        asyncio.run(_run())
    except BootstrapError as exc:
        print(f"Bootstrap остановлен: {exc}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Bootstrap прерван. Изменения отменены.")
        raise SystemExit(1) from None
    except Exception:
        print(
            "Bootstrap завершился ошибкой. Изменения отменены; "
            "проверьте подключение и журналы сервера."
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
