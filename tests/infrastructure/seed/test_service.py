import pytest
from sqlalchemy import func, select

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.seed.service import RZACSVSeedService


def make_row(
    *,
    full_name: str = "Тестовый холдинг",
    short_name: str = "Тестовый холдинг",
) -> dict[str, str]:
    return {
        "holding_full_name": full_name,
        "holding_short_name": short_name,
        "holding_sap_code": "",
    }

@pytest.mark.asyncio
async def test_get_or_create_holding_creates_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            service = RZACSVSeedService(session)

            holding = await service.get_or_create_holding(make_row())

            assert holding.id is not None
            assert holding.type == EnterpriseType.HOLDING
            assert holding.full_name == "Тестовый холдинг"
            assert holding.short_name == "Тестовый холдинг"
            assert holding.sap_code is None
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_holding_returns_existing_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Существующий холдинг",
                short_name="Существующий",
                sap_code="SAP-001",
            )

            session.add(holding)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_holding(
                make_row(
                    full_name="Существующий холдинг",
                    short_name="Другое название",
                )
            )

            assert result.id == holding.id
            assert result.short_name == "Существующий"
            assert result.sap_code == "SAP-001"

            count_result = await session.execute(
                select(func.count())
                .select_from(Enterprise)
                .where(
                    Enterprise.type == EnterpriseType.HOLDING,
                    Enterprise.full_name == "Существующий холдинг",
                    Enterprise.deleted_at.is_(None),
                )
            )

            assert count_result.scalar_one() == 1
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_holding_ignores_deleted_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            deleted_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Архивный холдинг",
                short_name="Архивный",
                deleted_at=func.now(),
            )

            session.add(deleted_holding)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_holding(
                make_row(
                    full_name="Архивный холдинг",
                    short_name="Новый холдинг",
                )
            )

            assert result.id != deleted_holding.id
            assert result.short_name == "Новый холдинг"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_branch_is_scoped_to_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            first_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Первый холдинг",
                short_name="Первый",
            )
            second_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Второй холдинг",
                short_name="Второй",
            )

            session.add_all([first_holding, second_holding])
            await session.flush()

            first_branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=first_holding.id,
                full_name="Свердловский филиал",
                short_name="Свердловский",
            )

            session.add(first_branch)
            await session.flush()

            service = RZACSVSeedService(session)

            second_branch = await service.get_or_create_branch(
                {
                    "branch_full_name": "Свердловский филиал",
                    "branch_short_name": "Свердловский",
                    "branch_sap_code": "",
                },
                holding_id=second_holding.id,
            )

            assert second_branch.id != first_branch.id
            assert second_branch.parent_id == second_holding.id
            assert second_branch.full_name == "Свердловский филиал"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_branch_returns_existing_branch() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Тестовый холдинг",
                short_name="Тестовый",
            )

            session.add(holding)
            await session.flush()

            branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Существующий филиал",
                short_name="Существующий",
                sap_code="OLD-SAP",
            )

            session.add(branch)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_branch(
                {
                    "branch_full_name": "Существующий филиал",
                    "branch_short_name": "Новое название",
                    "branch_sap_code": "NEW-SAP",
                },
                holding_id=holding.id,
            )

            assert result.id == branch.id
            assert result.short_name == "Существующий"
            assert result.sap_code == "OLD-SAP"
        finally:
            await transaction.rollback()