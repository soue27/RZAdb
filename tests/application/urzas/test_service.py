from datetime import date
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.urzas.schemas import URZADetails
from app.application.urzas.service import URZAService
from app.domain.enums import ElementBase, RoomCategory, URZACategory, URZAStatus
from app.domain.urza import URZA


@pytest.mark.asyncio
async def test_get_details_returns_urza_details() -> None:
    repository = AsyncMock()

    urza = URZA(
        id=uuid7(),
        connection_id=uuid7(),
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

    repository.get_by_id.return_value = urza

    service = URZAService(repository)

    result = await service.get_details(urza.id)

    assert isinstance(result, URZADetails)
    assert result.id == urza.id
    assert result.dispatch_name == "РЗА-1"
    assert result.rdu_subordination is True
    assert result.inventory_number == "INV-001"
    assert result.commissioning_date == date(2020, 1, 1)
    assert result.status is URZAStatus.IN_OPERATION
    assert result.element_base is ElementBase.MICROPROCESSOR
    assert result.category is URZACategory.II
    assert result.room_category is RoomCategory.I
    assert result.complexity is False

    repository.get_by_id.assert_awaited_once_with(urza.id)


@pytest.mark.asyncio
async def test_get_details_raises_when_urza_not_found() -> None:
    repository = AsyncMock()
    repository.get_by_id.return_value = None

    service = URZAService(repository)

    urza_id = uuid7()

    with pytest.raises(ObjectNotFoundError):
        await service.get_details(urza_id)

    repository.get_by_id.assert_awaited_once_with(urza_id)