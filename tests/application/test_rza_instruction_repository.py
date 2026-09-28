from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.rza_instructions.repository import (
    RZAInstructionRepository,
)
from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


@pytest.mark.asyncio
async def test_get_by_id(system_user_id):
    session = MagicMock()
    session.get = AsyncMock()

    instruction_id = uuid7()
    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=uuid7(),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    session.get.return_value = instruction

    repository = RZAInstructionRepository(session)

    result = await repository.get_by_id(instruction_id)

    assert result is instruction
    session.get.assert_awaited_once_with(
        RZAInstruction,
        instruction_id,
    )


@pytest.mark.asyncio
async def test_get_by_substation_id(system_user_id):
    session = MagicMock()
    session.scalar = AsyncMock()

    substation_id = uuid7()
    instruction = RZAInstruction(
        id=uuid7(),
        substation_id=substation_id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    session.scalar.return_value = instruction

    repository = RZAInstructionRepository(session)

    result = await repository.get_by_substation_id(substation_id)

    assert result is instruction
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_version_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    version_id = uuid7()
    version = MagicMock(spec=RZAInstructionVersion)

    session.get.return_value = version

    repository = RZAInstructionRepository(session)

    result = await repository.get_version_by_id(version_id)

    assert result is version
    session.get.assert_awaited_once_with(
        RZAInstructionVersion,
        version_id,
    )


@pytest.mark.asyncio
async def test_add_instruction(system_user_id):
    session = MagicMock()
    session.flush = AsyncMock()

    instruction = RZAInstruction(
        id=uuid7(),
        substation_id=uuid7(),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    repository = RZAInstructionRepository(session)

    result = await repository.add_instruction(instruction)

    assert result is instruction
    session.add.assert_called_once_with(instruction)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_version():
    session = MagicMock()
    session.flush = AsyncMock()

    version = MagicMock(spec=RZAInstructionVersion)

    repository = RZAInstructionRepository(session)

    result = await repository.add_version(version)

    assert result is version
    session.add.assert_called_once_with(version)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_version():
    session = MagicMock()
    session.scalar = AsyncMock()

    instruction_id = uuid7()
    version = MagicMock(spec=RZAInstructionVersion)

    session.scalar.return_value = version

    repository = RZAInstructionRepository(session)

    result = await repository.get_current_version(instruction_id)

    assert result is version
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_versions():
    session = MagicMock()
    session.scalars = AsyncMock()

    instruction_id = uuid7()

    version_2 = MagicMock(spec=RZAInstructionVersion)
    version_1 = MagicMock(spec=RZAInstructionVersion)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [
        version_2,
        version_1,
    ]
    session.scalars.return_value = scalars_result

    repository = RZAInstructionRepository(session)

    result = await repository.get_versions(instruction_id)

    assert result == [
        version_2,
        version_1,
    ]

    session.scalars.assert_awaited_once()
    scalars_result.all.assert_called_once()