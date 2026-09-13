from datetime import datetime
from uuid import uuid4

import pytest

from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType


class FakeTaskRepository:
    """Минимальный repository для тестирования бизнес-логики без PostgreSQL."""

    def __init__(self) -> None:
        self.tasks = []
        self.history = []
        self.session = self

    def add(self, entity) -> None:
        if entity.__class__.__name__ == "TaskHistory":
            self.history.append(entity)

    async def create(self, task) -> None:
        # UUID генерируется SQLAlchemy default только при INSERT,
        # поэтому для fake repository задаём его вручную.
        if task.id is None:
            task.id = uuid4()

        self.tasks.append(task)

    async def get_by_id(self, task_id):
        return next(
            (task for task in self.tasks if task.id == task_id),
            None,
        )

    async def save(self, task):
        return task


@pytest.fixture
def repository() -> FakeTaskRepository:
    return FakeTaskRepository()


@pytest.fixture
def service(repository: FakeTaskRepository) -> TaskService:
    return TaskService(repository)


@pytest.mark.asyncio
async def test_create_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    now = datetime(2026, 9, 13, 10, 0)

    urza_id = uuid4()
    created_by = uuid4()

    task = await service.create_task(
        urza_id=urza_id,
        work_type=TaskWorkType.OTD,
        created_by=created_by,
        now=now,
    )

    assert task.urza_id == urza_id
    assert task.work_type == TaskWorkType.OTD
    assert task.created_by == created_by
    assert task.status == TaskStatus.CREATED
    assert task.created_at == now
    assert task.deadline_at == datetime(2026, 9, 20, 10, 0)
    assert task.maintenance_type is None

    assert len(repository.history) == 1

    history = repository.history[0]

    assert history.task_id == task.id
    assert history.event_type == "created"
    assert history.old_status is None
    assert history.new_status == TaskStatus.CREATED
    assert history.actor_id == created_by
    assert history.created_at == now


@pytest.mark.asyncio
async def test_create_maintenance_task_requires_maintenance_type(
    service: TaskService,
) -> None:
    with pytest.raises(ValueError, match="maintenance_type"):
        await service.create_task(
            urza_id=uuid4(),
            work_type=TaskWorkType.MAINTENANCE,
            created_by=uuid4(),
        )


@pytest.mark.asyncio
async def test_non_maintenance_task_cannot_have_maintenance_type(
    service: TaskService,
) -> None:
    with pytest.raises(ValueError, match="maintenance_type"):
        await service.create_task(
            urza_id=uuid4(),
            work_type=TaskWorkType.OTD,
            created_by=uuid4(),
            maintenance_type=MaintenanceType.V,
        )


@pytest.mark.asyncio
async def test_create_maintenance_task(
    service: TaskService,
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        created_by=uuid4(),
        maintenance_type=MaintenanceType.K1,
    )

    assert task.work_type == TaskWorkType.MAINTENANCE
    assert task.maintenance_type == MaintenanceType.K1


@pytest.mark.asyncio
async def test_assign_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 14, 15, 30)

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=created_at,
    )

    original_deadline = task.deadline_at
    assigned_to = uuid4()
    actor_id = uuid4()

    await service.assign_task(
        task=task,
        assigned_to=assigned_to,
        actor_id=actor_id,
        assigned_at=assigned_at,
    )

    assert task.status == TaskStatus.ASSIGNED
    assert task.assigned_to == assigned_to
    assert task.assigned_at == assigned_at
    assert task.acceptance_deadline_at == datetime(2026, 9, 15, 15, 30)

    # Основной deadline считается от создания и при назначении не меняется.
    assert task.deadline_at == original_deadline

    assert len(repository.history) == 2

    history = repository.history[1]

    assert history.task_id == task.id
    assert history.event_type == "assigned"
    assert history.old_status == TaskStatus.CREATED
    assert history.new_status == TaskStatus.ASSIGNED
    assert history.actor_id == actor_id
    assert history.created_at == assigned_at

@pytest.mark.asyncio
async def test_assign_task_rejects_invalid_status(
    service: TaskService,
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=datetime(2026, 9, 13, 10, 0),
    )

    await service.assign_task(
        task=task,
        assigned_to=uuid4(),
        actor_id=uuid4(),
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.assign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=uuid4(),
            assigned_at=datetime(2026, 9, 13, 13, 0),
        )


@pytest.mark.asyncio
async def test_accept_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    accepted_at = datetime(2026, 9, 14, 9, 30)

    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=created_at,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
        assigned_at=assigned_at,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
        accepted_at=accepted_at,
    )

    assert task.status == TaskStatus.IN_PROGRESS

    # Acceptance deadline не меняется после принятия.
    assert task.acceptance_deadline_at == datetime(2026, 9, 14, 12, 0)

    # Основной deadline также остаётся от даты создания.
    assert task.deadline_at == datetime(2026, 9, 20, 10, 0)

    assert len(repository.history) == 4

    accepted_history = repository.history[2]
    assert accepted_history.event_type == "accepted"
    assert accepted_history.old_status == TaskStatus.ASSIGNED
    assert accepted_history.new_status == TaskStatus.IN_PROGRESS
    assert accepted_history.actor_id == engineer_id
    assert accepted_history.created_at == accepted_at

    started_history = repository.history[3]
    assert started_history.event_type == "started"
    assert started_history.old_status == TaskStatus.IN_PROGRESS
    assert started_history.new_status == TaskStatus.IN_PROGRESS
    assert started_history.actor_id == engineer_id
    assert started_history.created_at == accepted_at


@pytest.mark.asyncio
async def test_accept_task_only_by_assigned_engineer(
    service: TaskService,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=datetime(2026, 9, 13, 10, 0),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    with pytest.raises(ValueError, match="назначенный инженер"):
        await service.accept_task(
            task=task,
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_accept_task_rejects_invalid_status(
    service: TaskService,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=datetime(2026, 9, 13, 10, 0),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.accept_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_reject_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    rejected_at = datetime(2026, 9, 14, 9, 30)

    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=created_at,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
        assigned_at=assigned_at,
    )

    original_deadline = task.deadline_at

    await service.reject_task(
        task=task,
        actor_id=engineer_id,
        reason="Не могу выполнить задание в установленный срок.",
        rejected_at=rejected_at,
    )

    assert task.status == TaskStatus.REJECTED
    assert task.deadline_at == original_deadline

    assert len(repository.history) == 3

    history = repository.history[2]

    assert history.task_id == task.id
    assert history.event_type == "rejected"
    assert history.old_status == TaskStatus.ASSIGNED
    assert history.new_status == TaskStatus.REJECTED
    assert history.actor_id == engineer_id
    assert history.comment == "Не могу выполнить задание в установленный срок."
    assert history.created_at == rejected_at


@pytest.mark.asyncio
async def test_reject_task_requires_reason(
    service: TaskService,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Причина обязательна"):
        await service.reject_task(
            task=task,
            actor_id=engineer_id,
            reason="   ",
        )


@pytest.mark.asyncio
async def test_reject_task_only_by_assigned_engineer(
    service: TaskService,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
    )

    with pytest.raises(ValueError, match="назначенный инженер"):
        await service.reject_task(
            task=task,
            actor_id=uuid4(),
            reason="Нет возможности выполнить.",
        )


@pytest.mark.asyncio
async def test_reassign_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    first_assigned_at = datetime(2026, 9, 13, 12, 0)
    reassigned_at = datetime(2026, 9, 14, 9, 30)

    first_engineer_id = uuid4()
    second_engineer_id = uuid4()
    manager_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
        now=created_at,
    )

    await service.assign_task(
        task=task,
        assigned_to=first_engineer_id,
        actor_id=manager_id,
        assigned_at=first_assigned_at,
    )

    original_deadline = task.deadline_at

    await service.reassign_task(
        task=task,
        assigned_to=second_engineer_id,
        actor_id=manager_id,
        assigned_at=reassigned_at,
    )

    assert task.status == TaskStatus.ASSIGNED
    assert task.assigned_to == second_engineer_id
    assert task.assigned_at == reassigned_at

    # Срок принятия начинается заново для нового назначения.
    assert task.acceptance_deadline_at == datetime(2026, 9, 15, 9, 30)

    # Срок выполнения всей задачи от создания НЕ меняется.
    assert task.deadline_at == original_deadline

    assert len(repository.history) == 3

    history = repository.history[2]

    assert history.task_id == task.id
    assert history.event_type == "reassigned"
    assert history.old_status == TaskStatus.ASSIGNED
    assert history.new_status == TaskStatus.ASSIGNED
    assert history.actor_id == manager_id
    assert history.created_at == reassigned_at


@pytest.mark.asyncio
async def test_reassign_task_only_in_assigned_status(
    service: TaskService,
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
    )

    with pytest.raises(ValueError, match="назначенную задачу"):
        await service.reassign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=uuid4(),
        )

@pytest.mark.asyncio
async def test_reassign_task_requires_new_assignee(
    service: TaskService,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
    )

    with pytest.raises(ValueError, match="отличаться"):
        await service.reassign_task(
            task=task,
            assigned_to=engineer_id,
            actor_id=uuid4(),
        )