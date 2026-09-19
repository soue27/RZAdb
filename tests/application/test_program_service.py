from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.programs.service import ProgramService
from app.domain.enums import ProgramType
from app.domain.program import Program


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
    return ProgramService(
        repository=repository,
        access_service=access_service,
    )


@pytest.mark.asyncio
async def test_get_by_urza_returns_programs(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    programs = [
        MagicMock(spec=Program),
        MagicMock(spec=Program),
    ]

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=programs,
    )

    result = await service.get_by_urza(
        user_id,
        urza_id,
    )

    assert result == programs
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
async def test_get_by_id_returns_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = MagicMock(spec=Program)

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=program,
    )

    result = await service.get_by_id(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_id.assert_awaited_once_with(
        program_id,
    )


@pytest.mark.asyncio
async def test_get_by_id_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_id(
            user_id,
            program_id,
            urza_id,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_task_returns_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    program = MagicMock(spec=Program)

    access_service.can_access_urza.return_value = True
    repository.get_by_task_id = AsyncMock(
        return_value=program,
    )

    result = await service.get_by_task(
        user_id,
        task_id,
        urza_id,
    )

    assert result is program
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
async def test_create_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="ПР-001",
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        task_id=task_id,
    )

    assert isinstance(result, Program)
    assert result.urza_id == urza_id
    assert result.program_type == ProgramType.WORK
    assert result.program_number == "ПР-001"
    assert result.scan_file_id == scan_file_id
    assert result.editable_file_id == editable_file_id
    assert result.task_id == task_id

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_program_without_editable_file(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        program_type=ProgramType.COMMISSIONING,
        program_number="ВВ-001",
        scan_file_id=scan_file_id,
    )

    assert result.program_type == ProgramType.COMMISSIONING
    assert result.editable_file_id is None
    assert result.task_id is None

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_supports_all_program_types(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    for program_type in ProgramType:
        result = await service.create(
            user_id=uuid7(),
            urza_id=uuid7(),
            program_type=program_type,
            program_number=f"TEST-{program_type.value}",
            scan_file_id=uuid7(),
        )

        assert result.program_type == program_type

    assert repository.add.await_count == len(ProgramType)


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
            program_type=ProgramType.WORK,
            program_number="ПР-001",
            scan_file_id=uuid7(),
        )

    repository.add.assert_not_awaited()