from datetime import date

from uuid6 import uuid7

from app.application.urzas.schemas import URZADetails
from app.domain.enums import ElementBase, RoomCategory, URZACategory, URZAStatus


def test_urza_details() -> None:
    urza_id = uuid7()

    result = URZADetails(
        id=urza_id,
        dispatch_name="РЗА-1",
        rdu_subordination=True,
        inventory_number="INV-001",
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
    )

    assert result.id == urza_id
    assert result.dispatch_name == "РЗА-1"
    assert result.rdu_subordination is True
    assert result.inventory_number == "INV-001"
    assert result.commissioning_date == date(2020, 1, 1)
    assert result.status is URZAStatus.IN_OPERATION
    assert result.element_base is ElementBase.MICROPROCESSOR
    assert result.category is URZACategory.II
    assert result.room_category is RoomCategory.I
    assert result.complexity is False