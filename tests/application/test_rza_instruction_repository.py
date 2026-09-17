from unittest.mock import AsyncMock, MagicMock
from uuid6 import uuid7
import pytest

from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)
from app.application.rza_instructions.repository import (
    RZAInstructionRepository,
)

@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    instruction_id = uuid7()
    instruction = RZAInstruction(
        id=instruction_id,
        substation_id=uuid7(),
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
async def test_get_by_substation_id():
    session = MagicMock()
    session.scalar = AsyncMock()

    substation_id = uuid7()
    instruction = RZAInstruction(
        id=uuid7(),
        substation_id=substation_id,
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
async def test_add_instruction():
    session = MagicMock()
    session.flush = AsyncMock()

    instruction = RZAInstruction(
        id=uuid7(),
        substation_id=uuid7(),
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