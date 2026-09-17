from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.maintenance.repository import TORecordRepository
from app.domain.maintenance import TORecord


@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    record_id = uuid7()
    record = MagicMock(spec=TORecord)

    session.get.return_value = record

    repository = TORecordRepository(session)

    result = await repository.get_by_id(record_id)

    assert result is record
    session.get.assert_awaited_once_with(
        TORecord,
        record_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_id():
    session = MagicMock()
    session.scalars = AsyncMock()

    urza_id = uuid7()

    record_1 = MagicMock(spec=TORecord)
    record_2 = MagicMock(spec=TORecord)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [
        record_1,
        record_2,
    ]

    session.scalars.return_value = scalars_result

    repository = TORecordRepository(session)

    result = await repository.get_by_urza_id(urza_id)

    assert result == [
        record_1,
        record_2,
    ]
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_urza_id_returns_empty_list():
    session = MagicMock()
    session.scalars = AsyncMock()

    scalars_result = MagicMock()
    scalars_result.all.return_value = []

    session.scalars.return_value = scalars_result

    repository = TORecordRepository(session)

    result = await repository.get_by_urza_id(uuid7())

    assert result == []


@pytest.mark.asyncio
async def test_get_by_task_id():
    session = MagicMock()
    session.scalar = AsyncMock()

    task_id = uuid7()
    record = MagicMock(spec=TORecord)

    session.scalar.return_value = record

    repository = TORecordRepository(session)

    result = await repository.get_by_task_id(task_id)

    assert result is record
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_add():
    session = MagicMock()
    session.flush = AsyncMock()

    record = MagicMock(spec=TORecord)

    repository = TORecordRepository(session)

    result = await repository.add(record)

    assert result is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()
