from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.programs.repository import ProgramRepository
from app.domain.program import Program


@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    program_id = uuid7()
    program = MagicMock(spec=Program)

    session.get.return_value = program

    repository = ProgramRepository(session)

    result = await repository.get_by_id(program_id)

    assert result is program
    session.get.assert_awaited_once_with(
        Program,
        program_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_id():
    session = MagicMock()
    session.scalars = AsyncMock()

    urza_id = uuid7()

    program_1 = MagicMock(spec=Program)
    program_2 = MagicMock(spec=Program)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [
        program_1,
        program_2,
    ]

    session.scalars.return_value = scalars_result

    repository = ProgramRepository(session)

    result = await repository.get_by_urza_id(urza_id)

    assert result == [
        program_1,
        program_2,
    ]
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_urza_id_returns_empty_list():
    session = MagicMock()
    session.scalars = AsyncMock()

    scalars_result = MagicMock()
    scalars_result.all.return_value = []

    session.scalars.return_value = scalars_result

    repository = ProgramRepository(session)

    result = await repository.get_by_urza_id(uuid7())

    assert result == []


@pytest.mark.asyncio
async def test_get_by_task_id():
    session = MagicMock()
    session.scalar = AsyncMock()

    task_id = uuid7()
    program = MagicMock(spec=Program)

    session.scalar.return_value = program

    repository = ProgramRepository(session)

    result = await repository.get_by_task_id(task_id)

    assert result is program
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_add():
    session = MagicMock()
    session.flush = AsyncMock()

    program = MagicMock(spec=Program)

    repository = ProgramRepository(session)

    result = await repository.add(program)

    assert result is program
    session.add.assert_called_once_with(program)
    session.flush.assert_awaited_once()