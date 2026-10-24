from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.application.objects.archive_repository import ArchiveRepository
from app.domain.enums import TaskStatus


class _Rows:
    def all(self):
        return []


@pytest.mark.asyncio
async def test_blocker_queries_exclude_only_closed_and_rejected_processes():
    session = SimpleNamespace(scalars=AsyncMock(return_value=_Rows()))
    repository = ArchiveRepository(session)
    station_id, urza_id = uuid4(), uuid4()

    result = await repository.get_blocking_processes(
        substation_id=station_id,
        urza_ids=[urza_id],
        include_inspections=True,
    )

    assert result == []
    assert session.scalars.await_count == 2
    task_query = session.scalars.await_args_list[0].args[0]
    inspection_query = session.scalars.await_args_list[1].args[0]
    task_sql = str(task_query.compile(dialect=postgresql.dialect()))
    inspection_sql = str(inspection_query.compile(dialect=postgresql.dialect()))
    assert "tasks.substation_id" in task_sql
    assert "tasks.urza_id" in task_sql
    assert " OR " in task_sql
    assert "tasks.status NOT IN" in task_sql
    assert "inspection_tasks.status NOT IN" in inspection_sql
    parameters = list(task_query.compile(dialect=postgresql.dialect()).params.values())
    assert station_id in parameters
    assert [urza_id] in parameters
    assert any(
        isinstance(value, list)
        and set(value) == {TaskStatus.CLOSED, TaskStatus.REJECTED}
        for value in parameters
    )


@pytest.mark.asyncio
async def test_history_query_filters_object_and_uses_stable_event_order():
    session = SimpleNamespace(scalars=AsyncMock(return_value=_Rows()))
    repository = ArchiveRepository(session)
    object_id = uuid4()

    assert await repository.get_history("connection", object_id) == []

    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "archive_events.connection_id =" in sql
    assert "ORDER BY archive_events.occurred_at, archive_events.id" in sql
