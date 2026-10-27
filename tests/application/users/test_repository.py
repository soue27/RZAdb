from datetime import datetime, UTC

import pytest

from app.application.users.repository import UserRepository
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_get_by_email(system_user_id) -> None:
    async with async_session_factory() as session:
        user = User(
            full_name="Тестовый пользователь",
            role=UserRole.ENGINEER,
            email="repository@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
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




@pytest.mark.asyncio
async def test_get_all_returns_active_inactive_and_archived_users(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        active_user = User(
            full_name="Активный пользователь",
            role=UserRole.ENGINEER,
            email="active@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        inactive_user = User(
            full_name="Отключённый пользователь",
            role=UserRole.ENGINEER,
            email="inactive@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        archived_user = User(
            full_name="Архивный пользователь",
            role=UserRole.ENGINEER,
            email="archived@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
            deleted_at=datetime.now(UTC),
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add_all([active_user, inactive_user, archived_user])
        await session.flush()

        repository = UserRepository(session)
        users = await repository.get_all()
        users_by_email = {user.email: user for user in users}

        assert "active@test.local" in users_by_email
        assert "inactive@test.local" in users_by_email
        assert "archived@test.local" in users_by_email

        assert users_by_email["active@test.local"].active is True
        assert users_by_email["inactive@test.local"].active is False
        assert users_by_email["archived@test.local"].deleted_at is not None

        await session.rollback()


