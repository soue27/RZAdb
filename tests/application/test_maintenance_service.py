from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.maintenance.service import TORecordService
from app.domain.enums import MaintenanceType
from app.domain.maintenance import TORecord


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_urza = AsyncMock()
    return service


@pytest.fixture
def service(repository, access_service):
    return TORecordService(
        repository=repository,
        access_service=access_service,
    )


@pytest.mark.asyncio
async def test_get_by_urza_returns_records(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    records = [
        MagicMock(spec=TORecord),
        MagicMock(spec=TORecord),
    ]

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=records,
    )

    result = await service.get_by_urza(
        user_id,
        urza_id,
    )

    assert result == records
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_awaited_once_with(
        urza_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_urza_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_urza(
            user_id,
            urza_id,
        )

    repository.get_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_task_returns_record(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    record = MagicMock(spec=TORecord)

    access_service.can_access_urza.return_value = True
    repository.get_by_task_id = AsyncMock(
        return_value=record,
    )

    result = await service.get_by_task(
        user_id,
        task_id,
        urza_id,
    )

    assert result is record
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_task_id.assert_awaited_once_with(
        task_id,
    )


@pytest.mark.asyncio
async def test_get_by_task_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_task_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_task(
            user_id,
            task_id,
            urza_id,
        )

    repository.get_by_task_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_returns_record(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    record = MagicMock(spec=TORecord)

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=record,
    )

    result = await service.get_by_id(
        user_id,
        record_id,
        urza_id,
    )

    assert result is record
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_id.assert_awaited_once_with(
        record_id,
    )


@pytest.mark.asyncio
async def test_get_by_id_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_id(
            user_id,
            record_id,
            urza_id,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_requires_protocol_for_regular_maintenance(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    signed_form_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    with pytest.raises(
        ValueError,
        match="требуется протокол",
    ):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.V,
            signed_form_file_id=signed_form_file_id,
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_allows_maintenance_without_protocol_for_tk(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    signed_form_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=signed_form_file_id,
    )

    assert isinstance(result, TORecord)
    assert result.maintenance_type == MaintenanceType.TK
    assert result.scan_protocol_id is None
    assert result.signed_form_file_id == signed_form_file_id

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "maintenance_type",
    [
        MaintenanceType.O,
        MaintenanceType.OSM,
    ],
)
async def test_create_allows_maintenance_without_protocol_for_special_types(
    service,
    repository,
    access_service,
    maintenance_type,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=maintenance_type,
        signed_form_file_id=uuid7(),
    )

    assert isinstance(result, TORecord)
    assert result.maintenance_type == maintenance_type
    assert result.scan_protocol_id is None

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_saves_protocol_and_task(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_protocol_id = uuid7()
    editable_protocol_id = uuid7()
    signed_form_file_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.K,
        signed_form_file_id=signed_form_file_id,
        scan_protocol_id=scan_protocol_id,
        editable_protocol_id=editable_protocol_id,
        task_id=task_id,
    )

    assert result.urza_id == urza_id
    assert result.maintenance_type == MaintenanceType.K
    assert result.scan_protocol_id == scan_protocol_id
    assert result.editable_protocol_id == editable_protocol_id
    assert result.signed_form_file_id == signed_form_file_id
    assert result.task_id == task_id
    assert result.created_by == user_id

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_uses_default_values(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=uuid7(),
        urza_id=uuid7(),
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=uuid7(),
    )

    assert result.detected_deviations == "Не выявлено"
    assert result.measures_taken == "Не требуется"

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.add = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.TK,
            signed_form_file_id=uuid7(),
        )

    repository.add.assert_not_awaited()