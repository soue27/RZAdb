from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.application.connections.repository import ConnectionRepository
from app.application.connections.schemas import ConnectionCreate
from app.application.connections.service import (
    ConnectionNameConflictError,
    ConnectionService,
)
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType, HighestVoltage, OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_connection_persistence(system_user_id) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
            latitude=Decimal("56.123456"),
            longitude=Decimal("60.123456"),
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Ввод 110 кВ",
            sap_code="SAP-CONN-001",
            asureo_code="ASUREO-CONN-001",
            rdu_subordination=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(connection)
        await session.flush()

        assert connection.id is not None
        assert connection.substation_id == substation.id
        assert connection.dispatch_name == "Ввод 110 кВ"
        assert connection.sap_code == "SAP-CONN-001"
        assert connection.asureo_code == "ASUREO-CONN-001"
        assert connection.rdu_subordination is True

        await session.rollback()


@pytest.mark.parametrize(
    "deleted_states",
    [(None, None), (None, "archived"), ("archived", "archived")],
    ids=["active-active", "active-archived", "archived-archived"],
)
@pytest.mark.asyncio
async def test_connection_name_is_unique_per_substation_including_archived(
    system_user_id,
    deleted_states,
) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое отделение для уникальности",
            short_name=f"ДУ-{datetime.now(UTC).timestamp()}",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name=f"ПС Уникальность {datetime.now(UTC).timestamp()}",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        other_substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name=f"ПС Уникальность 2 {datetime.now(UTC).timestamp()}",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([substation, other_substation])
        await session.flush()
        deleted_at = datetime.now(UTC)
        session.add_all([
            Connection(
                substation_id=substation.id,
                dispatch_name="ВЛ 110 кВ",
                rdu_subordination=False,
                deleted_at=(deleted_at if deleted_states[0] else None),
                created_by=system_user_id,
                updated_by=system_user_id,
            ),
            Connection(
                substation_id=other_substation.id,
                dispatch_name="ВЛ 110 кВ",
                rdu_subordination=False,
                deleted_at=(deleted_at if deleted_states[0] else None),
                created_by=system_user_id,
                updated_by=system_user_id,
            ),
        ])
        await session.flush()
        session.add(Connection(
            substation_id=substation.id,
            dispatch_name=(
                " ВЛ 110 кВ " if deleted_states == (None, None) else "ВЛ 110 кВ"
            ),
            rdu_subordination=True,
            deleted_at=(deleted_at if deleted_states[1] else None),
            created_by=system_user_id,
            updated_by=system_user_id,
        ))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_unique_race_rolls_back_savepoint_and_keeps_session_usable(system_user_id) -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name=f"Department {datetime.now(UTC).timestamp()}",
            short_name=f"D-{datetime.now(UTC).timestamp()}",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name=f"PS-{datetime.now(UTC).timestamp()}",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        existing = Connection(
            substation=substation,
            dispatch_name="ВЛ 110 кВ",
            rdu_subordination=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(existing)
        await session.flush()

        class ConcurrentInsertRepository(ConnectionRepository):
            async def exists_by_name(self, substation_id, dispatch_name):
                return False

        service = ConnectionService(ConcurrentInsertRepository(session))
        assert session.in_transaction()
        with pytest.raises(ConnectionNameConflictError):
            await service.create(
                substation_id=substation.id,
                actor_id=system_user_id,
                data=ConnectionCreate(
                    dispatch_name=" ВЛ 110 кВ ",
                    rdu_subordination=True,
                ),
            )

        assert session.in_transaction()
        persisted_id = await session.scalar(
            select(Connection.id).where(Connection.id == existing.id)
        )
        assert persisted_id == existing.id
        await session.rollback()
