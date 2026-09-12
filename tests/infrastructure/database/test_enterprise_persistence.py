import pytest

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_enterprise_hierarchy() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Тестовый холдинг",
            short_name="Холдинг",
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Тестовый филиал",
            short_name="Филиал",
            parent=holding,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ПО",
            parent=branch,
        )

        session.add_all([holding, branch, department])
        await session.flush()

        assert holding.id is not None
        assert branch.id is not None
        assert department.id is not None

        assert branch.parent_id == holding.id
        assert department.parent_id == branch.id

        await session.rollback()