from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.presentation.dependencies.services import (
    get_auth_service,
    get_password_service,
)


def test_get_password_service() -> None:
    service = get_password_service()

    assert isinstance(service, PasswordService)


@pytest.mark.asyncio
async def test_get_auth_service() -> None:
    session = AsyncMock(spec=AsyncSession)
    password_service = PasswordService()

    with patch(
        "app.presentation.dependencies.services.UserRepository"
    ) as repository_class:
        service = get_auth_service(
            session=session,
            password_service=password_service,
        )

    assert isinstance(service, AuthService)
    assert service.password_service is password_service

    repository_class.assert_called_once_with(session)
    assert service.user_repository is repository_class.return_value