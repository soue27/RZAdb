from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from uuid6 import uuid7

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user


def make_request(session_data: dict) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
        }
    )

    request.scope["session"] = session_data
    return request


def make_user(
    *,
    active: bool = True,
    deleted_at=None,
    role: UserRole = UserRole.ENGINEER,
    system_user_id,
) -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=role,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=active,
        deleted_at=deleted_at,
        created_by=system_user_id,
        updated_by=system_user_id,
    )


@pytest.mark.asyncio
async def test_get_current_user_without_session() -> None:
    request = make_request({})

    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Требуется аутентификация."


@pytest.mark.asyncio
async def test_get_current_user_with_invalid_uuid() -> None:
    request = make_request({"user_id": "not-a-uuid"})

    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Недействительная сессия."


@pytest.mark.asyncio
async def test_get_current_user_when_user_not_found() -> None:
    user_id = uuid7()
    request = make_request({"user_id": str(user_id)})

    repository = AsyncMock()
    repository.get_by_id.return_value = None

    session = AsyncMock()

    with (
        patch(
            "app.presentation.auth.dependencies.UserRepository",
            return_value=repository,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Пользователь не найден или неактивен."


@pytest.mark.asyncio
async def test_get_current_user_when_user_inactive(system_user_id) -> None:
    user = make_user(active=False, system_user_id=system_user_id)

    request = make_request({"user_id": str(user.id)})

    repository = AsyncMock()
    repository.get_by_id.return_value = user

    session = AsyncMock()

    with (
        patch(
            "app.presentation.auth.dependencies.UserRepository",
            return_value=repository,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Пользователь не найден или неактивен."


@pytest.mark.asyncio
async def test_get_current_user_success(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)

    request = make_request({"user_id": str(user.id)})

    repository = AsyncMock()
    repository.get_by_id.return_value = user

    session = AsyncMock()

    with patch(
        "app.presentation.auth.dependencies.UserRepository",
        return_value=repository,
    ):
        result = await get_current_user(request, session)

    assert result is user
    repository.get_by_id.assert_awaited_once_with(user.id)

@pytest.mark.asyncio
async def test_require_superadmin_allows_superadmin(system_user_id) -> None:
    from app.presentation.auth.dependencies import require_superadmin

    user = make_user(
        role=UserRole.SUPERADMIN,
        system_user_id=system_user_id,
    )

    result = await require_superadmin(user)

    assert result is user


@pytest.mark.asyncio
async def test_require_superadmin_rejects_engineer(system_user_id) -> None:
    from app.presentation.auth.dependencies import require_superadmin

    user = make_user(system_user_id=system_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await require_superadmin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Недостаточно прав для выполнения этого действия."
    )