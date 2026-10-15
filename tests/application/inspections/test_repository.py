from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.inspections.repository import InspectionTaskRepository


@pytest.mark.asyncio
async def test_list_inspection_tasks_by_substation_returns_active_rows():
    tasks = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    session = MagicMock()
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: tasks))
    repository = InspectionTaskRepository(session)

    result = await repository.list_by_substation(uuid4())

    assert result == tasks
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_inspection_task_history_returns_ordered_rows():
    history = [SimpleNamespace(event_type="completed")]
    session = MagicMock()
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: history))
    repository = InspectionTaskRepository(session)

    assert await repository.get_history(uuid4()) == history
    session.scalars.assert_awaited_once()
