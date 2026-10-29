from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.users.repository import UserRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import AccessCategory, EnterpriseType, UserRole
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



@pytest.mark.asyncio
async def test_get_all_filters_by_enterprise(system_user_id) -> None:
    async with async_session_factory() as session:
        enterprise_a = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое предприятие А",
            short_name="Предприятие А",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        enterprise_b = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое предприятие Б",
            short_name="Предприятие Б",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([enterprise_a, enterprise_b])
        await session.flush()

        user_a = User(
            full_name="Инженер предприятия А",
            role=UserRole.ENGINEER,
            email="filter-enterprise-a@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise_a.id,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        user_b = User(
            full_name="Инженер предприятия Б",
            role=UserRole.ENGINEER,
            email="filter-enterprise-b@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise_b.id,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([user_a, user_b])
        await session.flush()

        users = await UserRepository(session).get_all(
            enterprise_id=enterprise_a.id,
        )
        emails = {user.email for user in users}

        assert "filter-enterprise-a@test.local" in emails
        assert "filter-enterprise-b@test.local" not in emails

        await session.rollback()


@pytest.mark.asyncio
async def test_get_all_filters_users_without_enterprise(system_user_id) -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Предприятие для теста",
            short_name="Предприятие",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(enterprise)
        await session.flush()

        user_with_enterprise = User(
            full_name="Пользователь с предприятием",
            role=UserRole.ENGINEER,
            email="filter-with-enterprise@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise.id,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        user_without_enterprise = User(
            full_name="Пользователь без предприятия",
            role=UserRole.ENGINEER,
            email="filter-without-enterprise@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([user_with_enterprise, user_without_enterprise])
        await session.flush()

        users = await UserRepository(session).get_all(
            without_enterprise=True,
        )
        emails = {user.email for user in users}

        assert "filter-without-enterprise@test.local" in emails
        assert "filter-with-enterprise@test.local" not in emails

        await session.rollback()


@pytest.mark.asyncio
async def test_get_all_combines_enterprise_role_and_status_filters(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Предприятие комбинированного фильтра",
            short_name="Предприятие комбинированного фильтра",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(enterprise)
        await session.flush()

        matching_user = User(
            full_name="Активный инженер",
            role=UserRole.ENGINEER,
            email="filter-combined-match@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise.id,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        inactive_user = User(
            full_name="Отключённый инженер",
            role=UserRole.ENGINEER,
            email="filter-combined-inactive@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise.id,
            access_category=AccessCategory.III,
            active=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        manager = User(
            full_name="Активный руководитель",
            role=UserRole.MANAGER,
            email="filter-combined-manager@test.local",
            password_hash="test-password-hash",
            enterprise_id=enterprise.id,
            access_category=AccessCategory.III,
            active=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([matching_user, inactive_user, manager])
        await session.flush()

        users = await UserRepository(session).get_all(
            role=UserRole.ENGINEER,
            status_filter="active",
            enterprise_id=enterprise.id,
        )
        emails = {user.email for user in users}

        assert "filter-combined-match@test.local" in emails
        assert "filter-combined-inactive@test.local" not in emails
        assert "filter-combined-manager@test.local" not in emails

        await session.rollback()


@pytest.mark.asyncio
async def test_email_digest_recipients_query_filters_roles_and_inactive_users():
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.scalars.return_value = result

    recipients = await UserRepository(
        session
    ).list_active_email_digest_recipients()

    assert recipients == []

    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "users.role IN" in sql
    assert "engineer" in sql
    assert "manager" in sql
    assert "users.active IS true" in sql
    assert "users.deleted_at IS NULL" in sql
    assert "users.email !=" in sql



