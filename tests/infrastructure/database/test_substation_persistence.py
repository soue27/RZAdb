from decimal import Decimal

import pytest

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType, HighestVoltage, OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_substation_persistence() -> None:
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
            sap_code="SAP-001",
            asureo_code="ASUREO-001",
            latitude=Decimal("56.123456"),
            longitude=Decimal("60.123456"),
            address="г. Екатеринбург, ул. Тестовая, 1",
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        session.add(substation)
        await session.flush()

        assert substation.id is not None
        assert substation.enterprise_id == department.id
        assert substation.highest_voltage == HighestVoltage.KV_110
        assert substation.dispatch_name == "ПС Тестовая"
        assert substation.sap_code == "SAP-001"
        assert substation.asureo_code == "ASUREO-001"
        assert substation.latitude == Decimal("56.123456")
        assert substation.longitude == Decimal("60.123456")

        await session.rollback()