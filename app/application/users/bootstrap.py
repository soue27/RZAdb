"""Одноразовое создание первого реального SUPERADMIN."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.password import PasswordService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.users.repository import UserRepository
from app.application.users.service import UserOperationError, UserService
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User

SYSTEM_ID = UUID("00000000-0000-7000-8000-000000000001")
SYSTEM_EMAIL = "system@rzadb.local"
_BOOTSTRAP_LOCK_KEY = 0x525A4144
_BOOTSTRAP_LOCK_SCOPE = 0x42535450


class BootstrapError(Exception):
    """Безопасный отказ процедуры первичного создания SUPERADMIN."""


@dataclass(frozen=True)
class BootstrapCredentials:
    full_name: str
    email: str
    password: str
    password_confirmation: str


CredentialsProvider = Callable[[], BootstrapCredentials]


async def bootstrap_superadmin(
    session: AsyncSession,
    credentials_provider: CredentialsProvider,
    password_service: PasswordService | None = None,
) -> User:
    """Проверяет состояние базы и атомарно создаёт первого SUPERADMIN.

    Блокировка PostgreSQL действует до фиксации или отката транзакции. Данные
    запрашиваются только после проверки SYSTEM и отсутствия других SUPERADMIN.
    Создание выполняет существующий UserService.
    """
    async with session.begin():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key, :lock_scope)"),
            {"lock_key": _BOOTSTRAP_LOCK_KEY, "lock_scope": _BOOTSTRAP_LOCK_SCOPE},
        )

        system_by_id = await session.get(User, SYSTEM_ID)
        system_by_email = await session.scalar(
            select(User).where(User.email == SYSTEM_EMAIL)
        )
        if (
            system_by_id is None
            or system_by_email is None
            or system_by_email.id != system_by_id.id
            or not _is_expected_system_user(system_by_id)
        ):
            raise BootstrapError(
                "Техническая запись SYSTEM отсутствует или имеет неверные свойства."
            )

        existing_superadmin = await session.scalar(
            select(User.id)
            .where(
                User.role == UserRole.SUPERADMIN,
                ~and_(User.id == SYSTEM_ID, User.email == SYSTEM_EMAIL),
            )
            .limit(1)
        )
        if existing_superadmin is not None:
            raise BootstrapError(
                "В базе уже есть реальный SUPERADMIN; повторный bootstrap запрещён."
            )

        credentials = credentials_provider()
        if credentials.password != credentials.password_confirmation:
            raise BootstrapError("Введённые пароли не совпадают.")
        if len(credentials.password) < 12:
            raise BootstrapError("Пароль должен содержать не менее 12 символов.")

        user_service = UserService(
            repository=UserRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            password_service=password_service or PasswordService(),
        )
        try:
            user = await user_service.create(
                actor=system_by_id,
                full_name=credentials.full_name,
                email=credentials.email,
                role=UserRole.SUPERADMIN,
                enterprise_id=None,
                access_category=AccessCategory.IV,
                temporary_password=credentials.password,
            )
        except UserOperationError as exc:
            raise BootstrapError(str(exc)) from None

    return user


def _is_expected_system_user(user: User) -> bool:
    return (
        user.id == SYSTEM_ID
        and user.email == SYSTEM_EMAIL
        and user.full_name == "SYSTEM"
        and user.role is UserRole.SUPERADMIN
        and user.enterprise_id is None
        and user.access_category is AccessCategory.IV
        and user.active is False
        and user.must_change_password is False
        and user.deleted_at is None
        and user.created_by == SYSTEM_ID
        and user.updated_by == SYSTEM_ID
    )
