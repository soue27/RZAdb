from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.maintenance.repository import TORecordRepository
from app.domain.maintenance import TORecord


@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.scalar = AsyncMock()
    record_id = uuid7()
    record = MagicMock(spec=TORecord)
    session.scalar.return_value = record

    assert await TORecordRepository(session).get_by_id(record_id) is record
    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "to_records.id" in sql
    assert "to_records.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_by_urza_id():
    session = MagicMock()
    session.scalars = AsyncMock()
    records = [MagicMock(spec=TORecord), MagicMock(spec=TORecord)]
    scalars_result = MagicMock()
    scalars_result.all.return_value = records
    session.scalars.return_value = scalars_result

    assert await TORecordRepository(session).get_by_urza_id(uuid7()) == records
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_urza_id_returns_empty_list():
    session = MagicMock()
    session.scalars = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    session.scalars.return_value = scalars_result

    assert await TORecordRepository(session).get_by_urza_id(uuid7()) == []


@pytest.mark.asyncio
async def test_list_by_urza_filters_archived_records():
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.scalars.return_value = result
    urza_id = uuid7()

    assert await TORecordRepository(session).get_by_urza_id(urza_id) == []
    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "to_records.urza_id" in sql
    assert "to_records.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_by_task_id_filters_archived_records():
    session = AsyncMock()
    session.scalar.return_value = None

    assert await TORecordRepository(session).get_by_task_id(uuid7()) is None
    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "to_records.task_id" in sql
    assert "to_records.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_by_task_id_returns_record():
    session = MagicMock()
    session.scalar = AsyncMock()
    record = MagicMock(spec=TORecord)
    session.scalar.return_value = record

    assert await TORecordRepository(session).get_by_task_id(uuid7()) is record
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_add():
    session = MagicMock()
    session.flush = AsyncMock()
    record = MagicMock(spec=TORecord)

    assert await TORecordRepository(session).add(record) is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()
