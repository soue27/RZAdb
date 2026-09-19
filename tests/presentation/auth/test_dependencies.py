from uuid6 import uuid7
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fastapi import HTTPException

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
) -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=active,
        deleted_at=deleted_at,
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

    with patch(
        "app.presentation.auth.dependencies.UserRepository",
        return_value=repository,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Пользователь не найден или неактивен."


@pytest.mark.asyncio
async def test_get_current_user_when_user_inactive() -> None:
    user = make_user(active=False)

    request = make_request({"user_id": str(user.id)})

    repository = AsyncMock()
    repository.get_by_id.return_value = user

    session = AsyncMock()

    with patch(
        "app.presentation.auth.dependencies.UserRepository",
        return_value=repository,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Пользователь не найден или неактивен."


@pytest.mark.asyncio
async def test_get_current_user_success() -> None:
    user = make_user()

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