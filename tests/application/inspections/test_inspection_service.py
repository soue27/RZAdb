from datetime import date
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.inspections.inspection_service import InspectionService
from app.domain.inspection import Inspection
from app.domain.inspection_task import InspectionTask


@pytest.mark.asyncio
async def test_get_by_substation_id() -> None:
    substation_id = uuid7()

    first_inspection = Inspection(
        id=uuid7(),
        substation_id=substation_id,
        inspection_task_id=uuid7(),
        inspection_date=date(2026, 8, 1),
        remarks="Первый осмотр",
        created_by=uuid7(),
    )

    second_inspection = Inspection(
        id=uuid7(),
        substation_id=substation_id,
        inspection_task_id=uuid7(),
        inspection_date=date(2026, 9, 1),
        remarks="Второй осмотр",
        created_by=uuid7(),
    )

    repository = AsyncMock()
    repository.get_by_substation_id.return_value = [
        second_inspection,
        first_inspection,
    ]

    service = InspectionService(repository)

    result = await service.get_by_substation_id(substation_id)

    assert result == [
        second_inspection,
        first_inspection,
    ]

    repository.get_by_substation_id.assert_awaited_once_with(
        substation_id,
    )