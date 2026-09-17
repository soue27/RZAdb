from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.urza_instructions.repository import (
    URZAInstructionRepository,
)
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    instruction_id = uuid7()
    instruction = URZAInstruction(
        id=instruction_id,
        urza_id=uuid7(),
    )

    session.get.return_value = instruction

    repository = URZAInstructionRepository(session)

    result = await repository.get_by_id(instruction_id)

    assert result is instruction
    session.get.assert_awaited_once_with(
        URZAInstruction,
        instruction_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_id():
    session = MagicMock()
    session.scalar = AsyncMock()

    urza_id = uuid7()
    instruction = URZAInstruction(
        id=uuid7(),
        urza_id=urza_id,
    )

    session.scalar.return_value = instruction

    repository = URZAInstructionRepository(session)

    result = await repository.get_by_urza_id(urza_id)

    assert result is instruction
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_version_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    version_id = uuid7()
    version = MagicMock(spec=URZAInstructionVersion)

    session.get.return_value = version

    repository = URZAInstructionRepository(session)

    result = await repository.get_version_by_id(version_id)

    assert result is version
    session.get.assert_awaited_once_with(
        URZAInstructionVersion,
        version_id,
    )


@pytest.mark.asyncio
async def test_add_instruction():
    session = MagicMock()
    session.flush = AsyncMock()

    instruction = URZAInstruction(
        id=uuid7(),
        urza_id=uuid7(),
    )

    repository = URZAInstructionRepository(session)

    result = await repository.add_instruction(instruction)

    assert result is instruction
    session.add.assert_called_once_with(instruction)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_version():
    session = MagicMock()
    session.flush = AsyncMock()

    version = MagicMock(spec=URZAInstructionVersion)

    repository = URZAInstructionRepository(session)

    result = await repository.add_version(version)

    assert result is version
    session.add.assert_called_once_with(version)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_version():
    session = MagicMock()
    session.scalar = AsyncMock()

    instruction_id = uuid7()
    version = MagicMock(spec=URZAInstructionVersion)

    session.scalar.return_value = version

    repository = URZAInstructionRepository(session)

    result = await repository.get_current_version(instruction_id)

    assert result is version
    session.scalar.assert_awaited_once()
