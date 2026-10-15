from datetime import UTC, datetime

import pytest
from uuid6 import uuid7

from app.application.connections.repository import ConnectionRepository
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType, HighestVoltage, OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_get_by_id_returns_connection(system_user_id) -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-110",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(connection)
        await session.flush()

        repository = ConnectionRepository(session)

        result = await repository.get_by_id(connection.id)

        assert result is not None
        assert result.id == connection.id
        assert result.dispatch_name == "Connection 1"

        await session.rollback()


@pytest.mark.asyncio
async def test_exists_by_name_includes_archived_connections_and_trims_name(system_user_id) -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name=f"Department {uuid7()}",
            short_name=f"D-{uuid7()}",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name=f"PS-{uuid7()}",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(substation)
        await session.flush()
        connection = Connection(
            substation_id=substation.id,
            dispatch_name="ВЛ 110 кВ",
            rdu_subordination=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(connection)
        await session.flush()
        repository = ConnectionRepository(session)

        assert await repository.exists_by_name(substation.id, "ВЛ 110 кВ")
        assert not await repository.exists_by_name(uuid7(), "ВЛ 110 кВ")
        connection.deleted_at = datetime.now(UTC)
        await session.flush()
        assert await repository.exists_by_name(substation.id, "ВЛ 110 кВ")
        await session.rollback()
