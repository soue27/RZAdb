from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.application.inspections.service import InspectionTaskService
from app.domain.enums import TaskStatus, UserRole


class FakeInspectionTaskRepository:
    def __init__(self) -> None:
        self.created_task = None

    async def create(self, task):
        self.created_task = task
        return task


@pytest.mark.asyncio
async def test_create_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    service = InspectionTaskService(repository)

    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)

    task = await service.create(
        substation_id=uuid4(),
        created_by=uuid4(),
        creator_role=UserRole.MANAGER,
        now=now,
    )

    assert task.status == TaskStatus.CREATED
    assert task.assigned_to is None
    assert task.assigned_at is None
    assert task.acceptance_deadline_at is None
    assert task.deadline_at == now + timedelta(days=7)
    assert repository.created_task is task


@pytest.mark.asyncio
async def test_only_manager_can_create_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    service = InspectionTaskService(repository)

    with pytest.raises(ValueError, match="только Manager"):
        await service.create(
            substation_id=uuid4(),
            created_by=uuid4(),
            creator_role=UserRole.ENGINEER,
        )