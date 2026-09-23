from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.inspections.inspection_service import InspectionService
from app.domain.file import File
from app.domain.inspection import Inspection


@pytest.mark.asyncio
async def test_get_by_substation_id() -> None:
    substation_id = uuid7()

    scan_file = File(
        id=uuid7(),
        s3_key="files/2026/08/scan.pdf",
        original_name="scan.pdf",
        display_name="Скан осмотра",
        extension=".pdf",
        size=1024,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )

    first_inspection = Inspection(
        id=uuid7(),
        substation_id=substation_id,
        inspection_task_id=uuid7(),
        inspection_date=date(2026, 8, 1),
        remarks="Первый осмотр",
        created_by=uuid7(),
        scan_file=scan_file,
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

    assert len(result) == 2

    assert result[0].id == second_inspection.id
    assert result[0].inspection_date == second_inspection.inspection_date
    assert result[0].remarks == second_inspection.remarks

    assert result[1].id == first_inspection.id
    assert result[1].inspection_date == first_inspection.inspection_date
    assert result[1].remarks == first_inspection.remarks
    assert result[1].scan_file_id == scan_file.id
    assert result[1].scan_file_name == "Скан осмотра"

    assert result[0].scan_file_id is None
    assert result[0].scan_file_name is None
    assert result[0].editable_file_id is None
    assert result[0].editable_file_name is None

    repository.get_by_substation_id.assert_awaited_once_with(
        substation_id,
    )