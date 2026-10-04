from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import MultipleResultsFound
from uuid6 import uuid7

from app.application.tasks.repository import TaskRepository


@pytest.mark.asyncio
async def test_get_schema_record_by_task_id_returns_active_record_only() -> None:
    session = AsyncMock()
    result = MagicMock()
    record = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute.return_value = result
    repository = TaskRepository(session)
    task_id = uuid7()

    assert await repository.get_schema_record_by_task_id(task_id) is record
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "schema_records.task_id" in sql
    assert "schema_records.deleted_at IS NULL" in sql
    result.scalar_one_or_none.assert_called_once()


@pytest.mark.asyncio
async def test_get_schema_record_by_task_id_preserves_no_result_contract() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    assert await TaskRepository(session).get_schema_record_by_task_id(uuid7()) is None


@pytest.mark.asyncio
async def test_get_schema_record_by_task_id_does_not_hide_duplicate_active_rows() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.side_effect = MultipleResultsFound
    session.execute.return_value = result

    with pytest.raises(MultipleResultsFound):
        await TaskRepository(session).get_schema_record_by_task_id(uuid7())


@pytest.mark.asyncio
async def test_list_active_tasks_filters_deleted_and_orders_newest_first() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    assert await TaskRepository(session).list_active() == []
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "tasks.deleted_at IS NULL" in sql
    assert "ORDER BY tasks.created_at DESC, tasks.id DESC" in sql


@pytest.mark.asyncio
async def test_get_active_task_by_id_filters_deleted_rows() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    assert await TaskRepository(session).get_active_by_id(uuid7()) is None
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "tasks.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_history_orders_events_and_loads_actor() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    task_id = uuid7()

    assert await TaskRepository(session).get_history(task_id) == []
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "task_history.task_id" in sql
    assert "ORDER BY task_history.created_at DESC, task_history.id DESC" in sql
