from unittest.mock import AsyncMock

import pytest

from app.application.auth.password import PasswordService
from app.application.auth.service import (
    AuthService,
    InvalidCredentialsError,
)
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User


@pytest.fixture
def password_service() -> PasswordService:
    return PasswordService()


@pytest.fixture
def user(password_service: PasswordService) -> User:
    return User(
        full_name="Тестовый инженер",
        role=UserRole.ENGINEER,
        email="engineer@test.local",
        password_hash=password_service.hash("StrongPassword123!"),
        enterprise_id=None,
        access_category=AccessCategory.III,
        active=True,
    )


@pytest.mark.asyncio
async def test_authenticate_success(
    password_service: PasswordService,
    user: User,
) -> None:
    repository = AsyncMock()
    repository.get_by_email.return_value = user

    service = AuthService(repository, password_service)

    result = await service.authenticate(
        email="engineer@test.local",
        password="StrongPassword123!",
    )

    assert result is user
    repository.get_by_email.assert_awaited_once_with("engineer@test.local")


@pytest.mark.asyncio
async def test_authenticate_unknown_email(
    password_service: PasswordService,
) -> None:
    repository = AsyncMock()
    repository.get_by_email.return_value = None

    service = AuthService(repository, password_service)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            email="unknown@test.local",
            password="StrongPassword123!",
        )


@pytest.mark.asyncio
async def test_authenticate_wrong_password(
    password_service: PasswordService,
    user: User,
) -> None:
    repository = AsyncMock()
    repository.get_by_email.return_value = user

    service = AuthService(repository, password_service)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            email="engineer@test.local",
            password="WrongPassword123!",
        )


@pytest.mark.asyncio
async def test_authenticate_inactive_user(
    password_service: PasswordService,
    user: User,
) -> None:
    user.active = False

    repository = AsyncMock()
    repository.get_by_email.return_value = user

    service = AuthService(repository, password_service)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            email="engineer@test.local",
            password="StrongPassword123!",
        )


@pytest.mark.asyncio
async def test_authenticate_deleted_user(
    password_service: PasswordService,
    user: User,
) -> None:
    from datetime import UTC, datetime

    user.deleted_at = datetime.now(UTC)

    repository = AsyncMock()
    repository.get_by_email.return_value = user

    service = AuthService(repository, password_service)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            email="engineer@test.local",
            password="StrongPassword123!",
        )