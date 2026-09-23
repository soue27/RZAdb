from datetime import date

from uuid6 import uuid7

from app.application.urzas.schemas import (
    URZAConnectionInfo,
    URZADetails,
    URZASubstationInfo,
)
from app.domain.enums import (
    ElementBase,
    RoomCategory,
    URZACategory,
    URZAStatus,
)


def test_urza_details() -> None:
    urza_id = uuid7()
    connection_id = uuid7()
    substation_id = uuid7()

    details = URZADetails(
        id=urza_id,
        dispatch_name="УРЗА-1",
        rdu_subordination=True,
        inventory_number="12345",
        commissioning_date="2026-01-01",
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        connection=URZAConnectionInfo(
            id=connection_id,
            dispatch_name="ВЛ 110 кВ",
        ),
        substation=URZASubstationInfo(
            id=substation_id,
            dispatch_name="ПС Центральная",
        ),
    )

    assert details.id == urza_id
    assert details.dispatch_name == "УРЗА-1"
    assert details.connection.id == connection_id
    assert details.connection.dispatch_name == "ВЛ 110 кВ"
    assert details.substation.id == substation_id
    assert details.substation.dispatch_name == "ПС Центральная"


def test_urza_details_contains_connection_and_substation() -> None:
    connection_id = uuid7()
    substation_id = uuid7()
    urza_id = uuid7()

    details = URZADetails(
        id=urza_id,
        dispatch_name="УРЗА-1",
        rdu_subordination=True,
        inventory_number="12345",
        commissioning_date="2026-01-01",
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        connection=URZAConnectionInfo(
            id=connection_id,
            dispatch_name="ВЛ 110 кВ",
        ),
        substation=URZASubstationInfo(
            id=substation_id,
            dispatch_name="ПС Центральная",
        ),
    )

    assert details.connection.id == connection_id
    assert details.connection.dispatch_name == "ВЛ 110 кВ"
    assert details.substation.id == substation_id
    assert details.substation.dispatch_name == "ПС Центральная"