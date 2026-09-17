from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.urza_instructions.service import (
    URZAInstructionService,
)
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


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
    return URZAInstructionService(
        repository=repository,
        access_service=access_service,
    )


@pytest.mark.asyncio
async def test_get_by_urza_returns_instruction(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    instruction = URZAInstruction(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=instruction,
    )

    result = await service.get_by_urza(
        user_id,
        urza_id,
    )

    assert result is instruction
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
async def test_create_instruction_with_first_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(return_value=None)
    repository.add_instruction = AsyncMock()
    repository.add_version = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        effective_date=date(2026, 9, 17),
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        change_description="Первичное создание",
        change_justification="Ввод инструкции",
    )

    assert isinstance(result, URZAInstruction)
    assert result.urza_id == urza_id

    repository.add_instruction.assert_awaited_once()

    created_instruction = repository.add_instruction.await_args.args[0]

    assert created_instruction.urza_id == urza_id

    repository.add_version.assert_awaited_once()

    created_version = repository.add_version.await_args.args[0]

    assert isinstance(created_version, URZAInstructionVersion)
    assert created_version.urza_instruction_id == created_instruction.id
    assert created_version.version_number == 1
    assert created_version.effective_date == date(2026, 9, 17)
    assert created_version.created_by == user_id
    assert created_version.scan_file_id == scan_file_id
    assert created_version.editable_file_id == editable_file_id
    assert created_version.change_description == "Первичное создание"
    assert created_version.change_justification == "Ввод инструкции"


@pytest.mark.asyncio
async def test_create_instruction_rejects_duplicate(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    existing = URZAInstruction(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=existing,
    )
    repository.add_instruction = AsyncMock()
    repository.add_version = AsyncMock()

    with pytest.raises(
        ValueError,
        match="уже существует",
    ):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.add_instruction.assert_not_awaited()
    repository.add_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_instruction_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_urza_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.get_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    instruction_id = uuid7()

    instruction = URZAInstruction(
        id=instruction_id,
        urza_id=urza_id,
    )

    version = MagicMock(spec=URZAInstructionVersion)

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=instruction,
    )
    repository.get_current_version = AsyncMock(
        return_value=version,
    )

    result = await service.get_current_version(
        user_id,
        urza_id,
    )

    assert result is version
    repository.get_current_version.assert_awaited_once_with(
        instruction_id,
    )


@pytest.mark.asyncio
async def test_get_current_version_without_instruction(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=None,
    )
    repository.get_current_version = AsyncMock()

    result = await service.get_current_version(
        user_id,
        urza_id,
    )

    assert result is None
    repository.get_current_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_version_increments_version_number(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    instruction_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()

    instruction = URZAInstruction(
        id=instruction_id,
        urza_id=urza_id,
    )

    current_version = URZAInstructionVersion(
        id=uuid7(),
        urza_instruction_id=instruction_id,
        version_number=3,
        effective_date=date(2026, 1, 1),
        created_by=user_id,
        scan_file_id=uuid7(),
    )

    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
    access_service.can_access_urza.return_value = True
    repository.get_current_version = AsyncMock(
        return_value=current_version,
    )
    repository.add_version = AsyncMock()

    result = await service.create_version(
        user_id=user_id,
        instruction_id=instruction_id,
        effective_date=date(2026, 9, 17),
        scan_file_id=scan_file_id,
    )

    assert isinstance(result, URZAInstructionVersion)
    assert result.urza_instruction_id == instruction_id
    assert result.version_number == 4
    assert result.effective_date == date(2026, 9, 17)
    assert result.created_by == user_id
    assert result.scan_file_id == scan_file_id

    repository.add_version.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_version_without_existing_version_creates_version_one(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    instruction_id = uuid7()
    urza_id = uuid7()

    instruction = URZAInstruction(
        id=instruction_id,
        urza_id=urza_id,
    )

    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
    access_service.can_access_urza.return_value = True
    repository.get_current_version = AsyncMock(
        return_value=None,
    )
    repository.add_version = AsyncMock()

    result = await service.create_version(
        user_id=user_id,
        instruction_id=instruction_id,
        effective_date=date(2026, 9, 17),
        scan_file_id=uuid7(),
    )

    assert result.version_number == 1
    repository.add_version.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_version_rejects_unknown_instruction(
    service,
    repository,
    access_service,
):
    instruction_id = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=None,
    )
    repository.add_version = AsyncMock()

    with pytest.raises(
        ValueError,
        match="не найдена",
    ):
        await service.create_version(
            user_id=uuid7(),
            instruction_id=instruction_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    access_service.can_access_urza.assert_not_awaited()
    repository.add_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_version_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    instruction_id = uuid7()
    urza_id = uuid7()

    instruction = URZAInstruction(
        id=instruction_id,
        urza_id=urza_id,
    )

    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
    access_service.can_access_urza.return_value = False
    repository.get_current_version = AsyncMock()
    repository.add_version = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create_version(
            user_id=user_id,
            instruction_id=instruction_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_current_version.assert_not_awaited()
    repository.add_version.assert_not_awaited()