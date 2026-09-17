from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid6 import uuid7
import pytest

from app.application.rza_instructions.service import RZAInstructionService
from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_substation = AsyncMock()
    return service


@pytest.fixture
def service(repository, access_service):
    return RZAInstructionService(
        repository=repository,
        access_service=access_service,
    )


@pytest.mark.asyncio
async def test_get_by_substation_returns_instruction(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    instruction = RZAInstruction(
        id=uuid7(),
        substation_id=substation_id,
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=instruction,
    )

    result = await service.get_by_substation(
        user_id,
        substation_id,
    )

    assert result is instruction
    access_service.can_access_substation.assert_awaited_once_with(
        user_id,
        substation_id,
    )
    repository.get_by_substation_id.assert_awaited_once_with(
        substation_id,
    )


@pytest.mark.asyncio
async def test_get_by_substation_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    access_service.can_access_substation.return_value = False
    repository.get_by_substation_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_substation(
            user_id,
            substation_id,
        )

    repository.get_by_substation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_instruction_with_first_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(return_value=None)
    repository.add_instruction = AsyncMock()
    repository.add_version = AsyncMock()

    result = await service.create(
        user_id=user_id,
        substation_id=substation_id,
        effective_date=date(2026, 9, 17),
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        change_description="Первичное создание",
        change_justification="Ввод инструкции",
    )

    assert isinstance(result, RZAInstruction)
    assert result.substation_id == substation_id

    repository.add_instruction.assert_awaited_once()

    created_instruction = repository.add_instruction.await_args.args[0]

    assert created_instruction.substation_id == substation_id

    repository.add_version.assert_awaited_once()

    created_version = repository.add_version.await_args.args[0]

    assert isinstance(created_version, RZAInstructionVersion)
    assert created_version.rza_instruction_id == created_instruction.id
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
    substation_id = uuid7()

    existing = RZAInstruction(
        id=uuid7(),
        substation_id=substation_id,
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
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
            substation_id=substation_id,
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
    substation_id = uuid7()

    access_service.can_access_substation.return_value = False
    repository.get_by_substation_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            substation_id=substation_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.get_by_substation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    instruction_id = uuid7()

    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=substation_id,
    )

    version = MagicMock(spec=RZAInstructionVersion)

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=instruction,
    )
    repository.get_current_version = AsyncMock(
        return_value=version,
    )

    result = await service.get_current_version(
        user_id,
        substation_id,
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
    substation_id = uuid7()

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=None,
    )
    repository.get_current_version = AsyncMock()

    result = await service.get_current_version(
        user_id,
        substation_id,
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
    substation_id = uuid7()
    scan_file_id = uuid7()

    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=substation_id,
    )

    current_version = RZAInstructionVersion(
        id=uuid7(),
        rza_instruction_id=instruction_id,
        version_number=3,
        effective_date=date(2026, 1, 1),
        created_by=user_id,
        scan_file_id=uuid7(),
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
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

    assert isinstance(result, RZAInstructionVersion)
    assert result.rza_instruction_id == instruction_id
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
    substation_id = uuid7()

    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=substation_id,
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
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

    access_service.can_access_substation.assert_not_awaited()
    repository.add_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_version_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    instruction_id = uuid7()
    substation_id = uuid7()

    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=substation_id,
    )

    repository.get_by_id = AsyncMock(
        return_value=instruction,
    )
    access_service.can_access_substation.return_value = False
    repository.add_version = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create_version(
            user_id=user_id,
            instruction_id=instruction_id,
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    access_service.can_access_substation.assert_awaited_once_with(
        user_id,
        substation_id,
    )
    repository.get_current_version.assert_not_called()
    repository.add_version.assert_not_awaited()
