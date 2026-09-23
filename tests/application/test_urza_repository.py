from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.urzas.repository import URZARepository
from app.domain.enums import ElementBase, RoomCategory, URZACategory, URZAStatus
from app.domain.urza import URZA


@pytest.mark.asyncio
async def test_get_by_id_returns_urza() -> None:
    session = AsyncMock()

    urza = URZA(
        id=uuid7(),
        connection_id=uuid7(),
        dispatch_name="РЗА-1",
        rdu_subordination=False,
        inventory_number=None,
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
    )

    scalars_result = MagicMock()
    scalars_result.one_or_none.return_value = urza
    session.scalars.return_value = scalars_result

    repository = URZARepository(session)

    result = await repository.get_by_id(urza.id)

    assert result is urza
    scalars_result.one_or_none.assert_called_once()