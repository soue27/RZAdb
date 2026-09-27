from datetime import date
from decimal import Decimal

import pytest

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_urza_persistence(system_user_id) -> None:
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
            rdu_subordination=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="ДЗЛ 110 кВ",
            rdu_subordination=False,
            inventory_number="INV-URZA-001",
            commissioning_date=date(2020, 5, 15),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add(urza)
        await session.flush()

        assert urza.id is not None
        assert urza.connection_id == connection.id
        assert urza.dispatch_name == "ДЗЛ 110 кВ"
        assert urza.rdu_subordination is False
        assert urza.inventory_number == "INV-URZA-001"
        assert urza.commissioning_date == date(2020, 5, 15)
        assert urza.status == URZAStatus.IN_OPERATION
        assert urza.element_base == ElementBase.MICROPROCESSOR
        assert urza.category == URZACategory.II
        assert urza.room_category == RoomCategory.I
        assert urza.complexity is True

        await session.rollback()
