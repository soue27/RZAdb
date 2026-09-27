import pytest

from app.application.enterprises.repository import EnterpriseRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_get_by_id(system_user_id) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(department)
        await session.flush()

        repository = EnterpriseRepository(session)

        result = await repository.get_by_id(department.id)

        assert result is not None
        assert result.id == department.id
        assert result.type == EnterpriseType.DEPARTMENT
        assert result.full_name == "Тестовое производственное отделение"

        await session.rollback()


@pytest.mark.asyncio
async def test_is_ancestor_or_same_returns_true_for_holding(system_user_id) -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Филиал",
            short_name="Ф",
            parent=holding,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Производственное отделение",
            short_name="ПО",
            parent=branch,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(department)
        await session.flush()

        repository = EnterpriseRepository(session)

        result = await repository.is_ancestor_or_same(
            ancestor_id=holding.id,
            enterprise_id=department.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_is_ancestor_or_same_returns_false_for_unrelated_enterprise(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        first_holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Первый Холдинг",
            short_name="Х1",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        second_holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Второй Холдинг",
            short_name="Х2",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО первого холдинга",
            short_name="ПО1",
            parent=first_holding,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add_all(
            [
                first_holding,
                second_holding,
                department,
            ]
        )
        await session.flush()

        repository = EnterpriseRepository(session)

        result = await repository.is_ancestor_or_same(
            ancestor_id=second_holding.id,
            enterprise_id=department.id,
        )

        assert result is False

        await session.rollback()


@pytest.mark.asyncio
async def test_is_ancestor_or_same_returns_true_for_same_enterprise(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО",
            short_name="ПО",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(department)
        await session.flush()

        repository = EnterpriseRepository(session)

        result = await repository.is_ancestor_or_same(
            ancestor_id=department.id,
            enterprise_id=department.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_is_ancestor_or_same_returns_false_when_department_is_checked_as_ancestor(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Филиал",
            short_name="Ф",
            parent=holding,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Производственное отделение",
            short_name="ПО",
            parent=branch,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(department)
        await session.flush()

        repository = EnterpriseRepository(session)

        result = await repository.is_ancestor_or_same(
            ancestor_id=department.id,
            enterprise_id=branch.id,
        )

        assert result is False

        await session.rollback()


@pytest.mark.asyncio
async def test_is_ancestor_or_same_ignores_deleted_enterprise(system_user_id) -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Удалённый филиал",
            short_name="УФ",
            parent=holding,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО",
            short_name="ПО",
            parent=branch,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(department)
        await session.flush()

        branch.deleted_at = branch.created_at

        repository = EnterpriseRepository(session)

        result = await repository.is_ancestor_or_same(
            ancestor_id=holding.id,
            enterprise_id=department.id,
        )

        assert result is False

        await session.rollback()
