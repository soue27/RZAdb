
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

import pytest

from app.application.inspections.service import InspectionTaskService
from app.domain.enums import AccessCategory, TaskStatus, UserRole
from app.domain.user import User


class FakeInspectionTaskRepository:
    def __init__(self) -> None:
        self.created_task = None
        self.tasks = {}
        self.history = []
        self.inspections = []

    async def create(self, task):
        self.created_task = task
        self.tasks[task.id] = task
        return task

    async def get_by_id(self, task_id):
        return self.tasks.get(task_id)

    async def save(self, task):
        self.tasks[task.id] = task
        return task

    async def add_history(self, history):
        self.history.append(history)
        return history

    async def create_inspection(self, inspection):
        self.inspections.append(inspection)
        return inspection


class FakeUserRepository:
    def __init__(self) -> None:
        self.users = {}

    async def get_by_id(self, user_id):
        return self.users.get(user_id)


def make_user(role: UserRole) -> User:
    """Создаёт минимального пользователя с явным ID для unit-тестов."""
    return User(
        id=uuid4(),
        full_name=f"Test {role.value}",
        role=role,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        access_category=AccessCategory.IV,
        active=True,
    )


@pytest.mark.asyncio
async def test_create_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    user_repository.users[manager.id] = manager

    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
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
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    engineer = make_user(UserRole.ENGINEER)
    user_repository.users[engineer.id] = engineer

    with pytest.raises(ValueError, match="только Manager"):
        await service.create(
            substation_id=uuid4(),
            created_by=engineer.id,
        )


@pytest.mark.asyncio
async def test_assign_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
        now=now,
    )

    assigned_task = await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=now,
    )

    assert assigned_task.status == TaskStatus.ASSIGNED
    assert assigned_task.assigned_to == engineer.id
    assert assigned_task.assigned_at == now
    assert assigned_task.acceptance_deadline_at == now + timedelta(days=1)
    assert assigned_task.deadline_at == now + timedelta(days=7)

    assert len(repository.history) == 1

    history = repository.history[0]

    assert history.inspection_task_id == task.id
    assert history.event_type == "assigned"
    assert history.old_status == TaskStatus.CREATED
    assert history.new_status == TaskStatus.ASSIGNED
    assert history.actor_id == manager.id


@pytest.mark.asyncio
async def test_only_manager_can_assign_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    with pytest.raises(ValueError, match="только Manager"):
        await service.assign(
            task.id,
            actor_id=engineer.id,
            assignee_id=engineer.id,
        )


@pytest.mark.asyncio
async def test_cannot_assign_non_engineer_or_manager() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    admin = make_user(UserRole.ADMIN)

    user_repository.users[manager.id] = manager
    user_repository.users[admin.id] = admin

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    with pytest.raises(ValueError, match="Engineer или Manager"):
        await service.assign(
            task.id,
            actor_id=manager.id,
            assignee_id=admin.id,
        )


@pytest.mark.asyncio
async def test_cannot_assign_already_assigned_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.assign(
            task.id,
            actor_id=manager.id,
            assignee_id=engineer.id,
        )

@pytest.mark.asyncio
async def test_assigned_engineer_can_accept_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
        now=now,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=now,
    )

    accepted_task = await service.accept(
        task.id,
        actor_id=engineer.id,
        now=now,
    )

    assert accepted_task.status == TaskStatus.IN_PROGRESS
    assert accepted_task.assigned_to == engineer.id
    assert accepted_task.acceptance_deadline_at == now + timedelta(days=1)
    assert accepted_task.deadline_at == now + timedelta(days=7)

    assert len(repository.history) == 2

    history = repository.history[1]

    assert history.event_type == "accepted"
    assert history.old_status == TaskStatus.ASSIGNED
    assert history.new_status == TaskStatus.IN_PROGRESS
    assert history.actor_id == engineer.id

@pytest.mark.asyncio
async def test_only_assigned_executor_can_accept_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)
    another_engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    user_repository.users[another_engineer.id] = another_engineer

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
    )

    with pytest.raises(
        ValueError,
        match="только назначенный исполнитель",
    ):
        await service.accept(
            task.id,
            actor_id=another_engineer.id,
        )

@pytest.mark.asyncio
async def test_assigned_engineer_can_complete_inspection_task() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
        now=now,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=now,
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
        now=now,
    )

    completed_task = await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
        now=now,
    )

    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.completed_at == now

    assert len(repository.inspections) == 1

    inspection = repository.inspections[0]

    assert inspection.substation_id == task.substation_id
    assert inspection.inspection_task_id == task.id
    assert inspection.inspection_date == date(2026, 9, 14)
    assert inspection.remarks == "Замечаний не выявлено."
    assert inspection.scan_file_id is None
    assert inspection.editable_file_id is None
    assert inspection.created_by == engineer.id

    assert len(repository.history) == 3

    history = repository.history[2]

    assert history.event_type == "completed"
    assert history.old_status == TaskStatus.IN_PROGRESS
    assert history.new_status == TaskStatus.COMPLETED
    assert history.actor_id == engineer.id

@pytest.mark.asyncio
async def test_inspection_cannot_be_completed_without_remarks() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
    )

    with pytest.raises(ValueError, match="замечания"):
        await service.complete(
            task.id,
            actor_id=engineer.id,
            inspection_date=date(2026, 9, 14),
            remarks="   ",
        )

@pytest.mark.asyncio
async def test_only_assigned_executor_can_complete_inspection() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    service = InspectionTaskService(repository, user_repository)

    manager = make_user(UserRole.MANAGER)
    engineer = make_user(UserRole.ENGINEER)
    another_engineer = make_user(UserRole.ENGINEER)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    user_repository.users[another_engineer.id] = another_engineer

    task = await service.create(
        substation_id=uuid4(),
        created_by=manager.id,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
    )

    with pytest.raises(
        ValueError,
        match="только назначенный исполнитель",
    ):
        await service.complete(
            task.id,
            actor_id=another_engineer.id,
            inspection_date=date(2026, 9, 14),
            remarks="Замечаний нет.",
        )