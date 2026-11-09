"""dependencies: зависимости и DTO presentation-слоя."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.users.repository import UserRepository
from app.core.request_context import bind_user_id
from app.domain.enums import UserRole
from app.domain.user import User
from app.infrastructure.database.session import get_session

PASSWORD_CHANGE_REQUIRED_DETAIL = (
    "Для продолжения необходимо сменить временный пароль."
)


class PasswordChangeRequired(HTTPException):
    """HTTP 403, используемый для ограничения доступа до обязательной смены временного пароля.
    """
    def __init__(self) -> None:
        """Создаёт HTTP 403 с единым сообщением о необходимости сменить временный пароль.
        """
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PASSWORD_CHANGE_REQUIRED_DETAIL,
        )


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Получает активного пользователя из сессии и привязывает его ID к request context.

    Разрешает доступ к маршруту смены пароля, если для пользователя установлено
    must_change_password; остальные маршруты блокируются.

    Args:
        request: HTTP-запрос с сессионными данными.
        session: Асинхронная SQLAlchemy-сессия.

    Returns:
        Активная учётная запись пользователя.

    Raises:
        HTTPException: Если сессия недействительна или пользователь неактивен.
        PasswordChangeRequired: Если пользователь должен сменить временный пароль.
    """
    user_id = request.session.get("user_id")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется аутентификация.",
        )

    try:
        user_uuid = UUID(str(user_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительная сессия.",
        ) from None

    user = await UserRepository(session).get_by_id(user_uuid)

    if user is None or user.deleted_at is not None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или неактивен.",
        )

    if user.must_change_password and request.url.path not in {
        "/auth/change-password",
    }:
        raise PasswordChangeRequired

    bind_user_id(str(user.id))
    return user


async def require_non_specialist(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Запрещает доступ пользователям с ролью SPECIALIST.

    Args:
        current_user: Пользователь, полученный через get_current_user.

    Returns:
        Текущий пользователь, если его роль не SPECIALIST.

    Raises:
        HTTPException: Если текущая роль — SPECIALIST.
    """
    if current_user.role is UserRole.SPECIALIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения этого действия.",
        )
    return current_user


async def require_superadmin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Разрешает доступ только пользователю с ролью SUPERADMIN."""

    if current_user.role is not UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения этого действия.",
        )

    return current_user
