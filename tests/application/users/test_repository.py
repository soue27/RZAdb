import pytest

from app.application.users.repository import UserRepository
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_get_by_email() -> None:
    async with async_session_factory() as session:
        user = User(
            full_name="Тестовый пользователь",
            role=UserRole.ENGINEER,
            email="repository@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
        )

        session.add(user)
        await session.flush()

        repository = UserRepository(session)

        result = await repository.get_by_email("repository@test.local")

        assert result is not None
        assert result.id == user.id
        assert result.email == "repository@test.local"

        await session.rollback()


@pytest.mark.asyncio
async def test_get_by_email_returns_none_for_unknown_email() -> None:
    async with async_session_factory() as session:
        repository = UserRepository(session)

        result = await repository.get_by_email("unknown@test.local")

        assert result is None