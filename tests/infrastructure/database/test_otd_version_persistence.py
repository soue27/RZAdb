from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    OTDPurpose,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.domain.otd import OTD, OTDVersion
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_otd_version_persistence() -> None:
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

            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Ввод 110 кВ",
            rdu_subordination=True,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="ДЗЛ 110 кВ",
            rdu_subordination=False,
            commissioning_date=date(2020, 5, 15),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=True,
        )

        otd = OTD(urza=urza)

        version_1 = OTDVersion(
            otd=otd,
            version_number=1,
            effective_date=date(2020, 5, 15),
            panel_cabinet_type="Шкаф РЗА",
            panel_cabinet_serial="PANEL-001",
            panel_cabinet_manufacture_year=2020,
            terminal_type="МП терминал",
            terminal_serial="TERM-001",
            terminal_manufacture_year=2020,
            urza_service_life=25,
            software_version="1.0.0",
            ct_ratio="600/5",
            vt_ratio="110000/100",
            urza_scheme_designation="ДЗЛ-110",
            urza_purpose=OTDPurpose.RZA,
        )

        version_2 = OTDVersion(
            otd=otd,
            version_number=2,
            effective_date=date(2025, 3, 10),
            panel_cabinet_type="Шкаф РЗА",
            panel_cabinet_serial="PANEL-001",
            panel_cabinet_manufacture_year=2020,
            terminal_type="МП терминал",
            terminal_serial="TERM-002",
            terminal_manufacture_year=2025,
            urza_service_life=25,
            software_version="2.0.0",
            ct_ratio="600/5",
            vt_ratio="110000/100",
            urza_scheme_designation="ДЗЛ-110",
            urza_purpose=OTDPurpose.RZA,
        )

        session.add_all([version_1, version_2])
        await session.flush()

        assert version_1.id is not None
        assert version_2.id is not None

        assert version_1.otd_id == otd.id
        assert version_2.otd_id == otd.id

        assert version_1.version_number == 1
        assert version_2.version_number == 2

        assert version_1.effective_date == date(2020, 5, 15)
        assert version_2.effective_date == date(2025, 3, 10)

        assert version_1.terminal_serial == "TERM-001"
        assert version_2.terminal_serial == "TERM-002"

        assert version_1.urza_purpose == OTDPurpose.RZA
        assert version_2.urza_purpose == OTDPurpose.RZA

        result = await session.execute(
            select(OTDVersion)
            .where(OTDVersion.otd_id == otd.id)
            .order_by(OTDVersion.version_number)
        )

        versions = result.scalars().all()

        assert len(versions) == 2
        assert versions[0].version_number == 1
        assert versions[1].version_number == 2

        await session.rollback()