import pytest

from uuid6 import uuid7

from app.application.connections.repository import ConnectionRepository
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType, HighestVoltage, OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_get_by_id_returns_connection() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )

        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-110",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        session.add(connection)
        await session.flush()

        repository = ConnectionRepository(session)

        result = await repository.get_by_id(connection.id)

        assert result is not None
        assert result.id == connection.id
        assert result.dispatch_name == "Connection 1"

        await session.rollback()