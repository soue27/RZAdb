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
async def test_get_to_record_by_task_id_filters_archived_results() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    task_id = uuid7()

    assert await TaskRepository(session).get_to_record_by_task_id(task_id) is None
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "to_records.task_id" in sql
    assert "to_records.deleted_at IS NULL" in sql


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
    eager_relationships = {
        str(option.path).split(" -> ")[1]
        for option in statement._with_options
    }
    assert eager_relationships == {
        "TaskHistory.actor",
        "TaskHistory.previous_assignee",
        "TaskHistory.new_assignee",
    }


@pytest.mark.asyncio
async def test_dashboard_task_count_is_aggregated_and_scoped_to_engineer():
    from datetime import UTC, datetime

    from app.domain.enums import TaskStatus, UserRole

    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = (0, 0, 0, 2, 0, 0, 0, 1)
    session.execute.return_value = result
    repository = TaskRepository(session)
    user_id, enterprise_id = uuid7(), uuid7()

    counts, overdue = await repository.count_dashboard_statuses(
        user_id=user_id,
        role=UserRole.ENGINEER,
        enterprise_ids={enterprise_id},
        now=datetime.now(UTC),
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "CASE WHEN (tasks.status = 'under_review'" in sql
    assert "tasks.assigned_to =" in sql
    assert "tasks.deleted_at IS NULL" in sql
    assert "tasks.deadline_at" in sql
    assert "closed" in sql and "rejected" in sql
    # List access is allowed for archived URZA when its parent remains
    # accessible; dashboard counts must not silently drop those tasks.
    assert "urzas_1.deleted_at IS NULL" not in sql
    assert "substations_1.enterprise_id IN" in sql
    assert counts[TaskStatus.UNDER_REVIEW] == 2
    assert overdue == 1



@pytest.mark.asyncio
async def test_email_digest_engineer_query_is_scoped_to_assignee() -> None:
    from app.domain.enums import TaskStatus

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    user_id = uuid7()

    assert await TaskRepository(
        session
    ).list_for_email_digest_engineer(user_id) == []

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "tasks.assigned_to =" in sql
    assert "tasks.deleted_at IS NULL" in sql
    assert "tasks.status IN" in sql
    assert all(
        status.value in sql
        for status in (
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
        )
    )
    assert "ORDER BY tasks.deadline_at ASC NULLS LAST" in sql


@pytest.mark.asyncio
async def test_email_digest_manager_query_is_scoped_to_enterprise() -> None:
    from app.domain.enums import TaskStatus

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    enterprise_id = uuid7()

    assert await TaskRepository(
        session
    ).list_for_email_digest_manager(enterprise_id) == []

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "tasks.deleted_at IS NULL" in sql
    assert "tasks.status IN" in sql
    assert "urzas" in sql
    assert "connections" in sql
    assert "substations" in sql
    assert all(
        status.value in sql
        for status in (
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
        )
    )
    assert "ORDER BY tasks.deadline_at ASC NULLS LAST" in sql

