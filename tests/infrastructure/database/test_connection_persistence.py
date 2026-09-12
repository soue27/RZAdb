from decimal import Decimal

import pytest

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType, HighestVoltage, OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_connection_persistence() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
            latitude=Decimal("56.123456"),
            longitude=Decimal("60.123456"),
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Ввод 110 кВ",
            sap_code="SAP-CONN-001",
            asureo_code="ASUREO-CONN-001",
            rdu_subordination=True,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        session.add(connection)
        await session.flush()

        assert connection.id is not None
        assert connection.substation_id == substation.id
        assert connection.dispatch_name == "Ввод 110 кВ"
        assert connection.sap_code == "SAP-CONN-001"
        assert connection.asureo_code == "ASUREO-CONN-001"
        assert connection.rdu_subordination is True
        assert (
            connection.operational_current_type
            == OperationalCurrentType.PERMANENT
        )

        await session.rollback()