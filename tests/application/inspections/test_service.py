from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from types import SimpleNamespace

import pytest
from uuid6 import uuid7

from app.application.inspections.service import InspectionTaskService
from app.application.urzas.service import URZAService
from app.domain.enums import AccessCategory, HighestVoltage, TaskStatus, UserRole, URZAStatus, ElementBase, \
    URZACategory, RoomCategory
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.domain.user import User
from app.application.urzas.schemas import URZACreate, URZADetails


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

    async def refresh_for_mutation(self, task):
        return task

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


@pytest.fixture
def service_dependencies():
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    return service, repository, user_repository, substation_repository


def make_user(role: UserRole, system_user_id) -> User:
    """Создаёт минимального пользователя с явным ID для unit-тестов."""
    return User(
        id=uuid4(),
        full_name=f"Test {role.value}",
        role=role,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )


class FakeSubstationRepository:
    def __init__(self) -> None:
        self.substations = {}

    async def get_by_id(self, substation_id):
        return self.substations.get(substation_id)

    async def lock_active_by_id(self, substation_id):
        substation = await self.get_by_id(substation_id)
        return substation is None or substation.deleted_at is None


@pytest.mark.asyncio
async def test_create_inspection_task_rejects_archived_substation() -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository, user_repository, substation_repository
    )
    actor_id = uuid4()
    substation_id = uuid4()
    user_repository.users[actor_id] = SimpleNamespace(role=UserRole.MANAGER)
    substation_repository.substations[substation_id] = SimpleNamespace(
        id=substation_id, deleted_at=datetime.now(UTC)
    )

    with pytest.raises(PermissionError, match="архивной подстанции"):
        await service.create(substation_id=substation_id, actor_id=actor_id)

    assert repository.created_task is None


@pytest.mark.asyncio
async def test_inspection_task_mutation_locks_substation_before_refresh():
    calls = []
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository, user_repository, substation_repository
    )
    task = SimpleNamespace(id=uuid4(), substation_id=uuid4(), deleted_at=None)
    repository.tasks[task.id] = task

    async def lock_active_by_id(substation_id):
        calls.append(("owner_lock", substation_id))
        return True

    async def refresh_for_mutation(current_task):
        calls.append(("task_refresh", current_task.id))
        return current_task

    substation_repository.lock_active_by_id = lock_active_by_id
    repository.refresh_for_mutation = refresh_for_mutation

    await service._lock_task_owner(task.id)

    assert calls == [
        ("owner_lock", task.substation_id),
        ("task_refresh", task.id),
    ]


@pytest.mark.asyncio
async def test_create_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    user_repository.users[manager.id] = manager

    now = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
        now=now,
    )

    assert task.status == TaskStatus.CREATED
    assert task.assigned_to is None
    assert task.assigned_at is None
    assert task.acceptance_deadline_at is None
    assert task.deadline_at == now + timedelta(days=7)
    assert task.created_by == manager.id
    assert task.updated_by == manager.id
    assert repository.created_task is task


@pytest.mark.asyncio
async def test_only_manager_can_create_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    engineer = make_user(UserRole.ENGINEER, system_user_id)
    user_repository.users[engineer.id] = engineer

    with pytest.raises(ValueError, match="только Manager"):
        await service.create(
            substation_id=uuid4(),
            actor_id=engineer.id,
        )


@pytest.mark.asyncio
async def test_assign_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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
async def test_only_manager_can_assign_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
    )

    with pytest.raises(ValueError, match="только Manager"):
        await service.assign(
            task.id,
            actor_id=engineer.id,
            assignee_id=engineer.id,
        )


@pytest.mark.asyncio
async def test_cannot_assign_non_engineer_or_manager(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    admin = make_user(UserRole.ADMIN, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[admin.id] = admin

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
    )

    with pytest.raises(ValueError, match="Engineer или Manager"):
        await service.assign(
            task.id,
            actor_id=manager.id,
            assignee_id=admin.id,
        )


@pytest.mark.asyncio
async def test_cannot_assign_already_assigned_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
    )

    assert task.updated_by == manager.id

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.assign(
            task.id,
            actor_id=manager.id,
            assignee_id=engineer.id,
        )


@pytest.mark.asyncio
async def test_assigned_engineer_can_accept_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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
async def test_only_assigned_executor_can_accept_inspection_task(
    system_user_id,
) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)
    another_engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    user_repository.users[another_engineer.id] = another_engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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
async def test_assigned_engineer_can_complete_inspection_task(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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

    assert task.updated_by == engineer.id

    completed_task = await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
        now=now,
    )

    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.completed_at == now
    assert completed_task.updated_by == engineer.id

    assert len(repository.inspections) == 1

    inspection = repository.inspections[0]

    assert inspection.substation_id == task.substation_id
    assert inspection.inspection_task_id == task.id
    assert inspection.inspection_date == date(2026, 9, 14)
    assert inspection.remarks == "Замечаний не выявлено."
    assert inspection.scan_file_id is None
    assert inspection.editable_file_id is None
    assert inspection.created_by == engineer.id
    assert inspection.updated_by == engineer.id

    assert len(repository.history) == 3

    history = repository.history[2]

    assert history.event_type == "completed"
    assert history.old_status == TaskStatus.IN_PROGRESS
    assert history.new_status == TaskStatus.COMPLETED
    assert history.actor_id == engineer.id


@pytest.mark.asyncio
async def test_inspection_cannot_be_completed_without_remarks(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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
async def test_only_assigned_executor_can_complete_inspection(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)
    another_engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    user_repository.users[another_engineer.id] = another_engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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


@pytest.mark.asyncio
async def test_assigned_engineer_can_send_inspection_to_review(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
        now=now,
    )

    reviewed_task = await service.send_to_review(
        task.id,
        actor_id=engineer.id,
        now=now,
    )

    assert reviewed_task.status == TaskStatus.UNDER_REVIEW
    assert reviewed_task.assigned_to == engineer.id
    assert reviewed_task.completed_at == now
    assert reviewed_task.deadline_at == now + timedelta(days=7)

    assert len(repository.history) == 4

    history = repository.history[3]

    assert history.event_type == "sent_to_review"
    assert history.old_status == TaskStatus.COMPLETED
    assert history.new_status == TaskStatus.UNDER_REVIEW
    assert history.actor_id == engineer.id


@pytest.mark.asyncio
async def test_only_assigned_executor_can_send_inspection_to_review(
    system_user_id,
) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)
    another_engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    user_repository.users[another_engineer.id] = another_engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
    )

    with pytest.raises(
        ValueError,
        match="только назначенный исполнитель",
    ):
        await service.send_to_review(
            task.id,
            actor_id=another_engineer.id,
        )


@pytest.mark.asyncio
async def test_cannot_send_in_progress_inspection_to_review(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer

    task = await service.create(
        substation_id=uuid4(),
        actor_id=manager.id,
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

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.send_to_review(
            task.id,
            actor_id=engineer.id,
        )


@pytest.mark.asyncio
async def test_manager_can_approve_inspection(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    substation_id = uuid4()
    department_id = uuid4()

    manager.enterprise_id = department_id

    substation = Substation(
        id=substation_id,
        enterprise_id=department_id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    substation_repository.substations[substation_id] = substation

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=substation_id,
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
        now=now,
    )

    await service.send_to_review(
        task.id,
        actor_id=engineer.id,
        now=now,
    )

    result = await service.review(
        task.id,
        actor_id=manager.id,
        approve=True,
        now=now,
    )

    assert result.status == TaskStatus.CLOSED
    assert result.closed_at == now

    history = repository.history[-1]

    assert history.event_type == "review_approved"
    assert history.old_status == TaskStatus.UNDER_REVIEW
    assert history.new_status == TaskStatus.CLOSED
    assert history.actor_id == manager.id


@pytest.mark.asyncio
async def test_manager_can_return_inspection_for_revision(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    substation_id = uuid4()
    department_id = uuid4()

    manager.enterprise_id = department_id

    substation = Substation(
        id=substation_id,
        enterprise_id=department_id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    substation_repository.substations[substation_id] = substation

    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    task = await service.create(
        substation_id=substation_id,
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Выявлено замечание.",
        now=now,
    )

    await service.send_to_review(
        task.id,
        actor_id=engineer.id,
        now=now,
    )

    reason = "Необходимо уточнить выявленные замечания."

    result = await service.review(
        task.id,
        actor_id=manager.id,
        approve=False,
        reason=reason,
        now=now,
    )

    assert result.status == TaskStatus.IN_PROGRESS
    assert result.closed_at is None
    assert result.completed_at == now
    assert result.deadline_at == now + timedelta(days=7)

    history = repository.history[-1]

    assert history.event_type == "review_rejected"
    assert history.old_status == TaskStatus.UNDER_REVIEW
    assert history.new_status == TaskStatus.IN_PROGRESS
    assert history.actor_id == manager.id
    assert history.comment == reason


@pytest.mark.asyncio
async def test_cannot_return_inspection_without_reason(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    substation_id = uuid4()
    department_id = uuid4()

    manager.enterprise_id = department_id

    substation = Substation(
        id=substation_id,
        enterprise_id=department_id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    user_repository.users[manager.id] = manager
    user_repository.users[engineer.id] = engineer
    substation_repository.substations[substation_id] = substation

    task = await service.create(
        substation_id=substation_id,
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
    )

    await service.send_to_review(
        task.id,
        actor_id=engineer.id,
    )

    with pytest.raises(ValueError, match="Необходимо указать причину"):
        await service.review(
            task.id,
            actor_id=manager.id,
            approve=False,
        )


@pytest.mark.asyncio
async def test_manager_from_another_department_cannot_review_inspection(
    system_user_id,
) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    another_manager = make_user(UserRole.MANAGER, system_user_id)
    engineer = make_user(UserRole.ENGINEER, system_user_id)

    substation_id = uuid4()

    department_id = uuid4()
    another_department_id = uuid4()

    manager.enterprise_id = department_id
    another_manager.enterprise_id = another_department_id

    substation = Substation(
        id=substation_id,
        enterprise_id=department_id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    user_repository.users[manager.id] = manager
    user_repository.users[another_manager.id] = another_manager
    user_repository.users[engineer.id] = engineer
    substation_repository.substations[substation_id] = substation

    task = await service.create(
        substation_id=substation_id,
        actor_id=manager.id,
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

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=date(2026, 9, 14),
        remarks="Замечаний не выявлено.",
    )

    await service.send_to_review(
        task.id,
        actor_id=engineer.id,
    )

    with pytest.raises(
        ValueError,
        match="тому же производственному отделению",
    ):
        await service.review(
            task.id,
            actor_id=another_manager.id,
            approve=True,
        )


@pytest.mark.asyncio
async def test_manager_cannot_review_own_inspection(system_user_id) -> None:
    repository = FakeInspectionTaskRepository()
    user_repository = FakeUserRepository()
    substation_repository = FakeSubstationRepository()

    service = InspectionTaskService(
        repository,
        user_repository,
        substation_repository,
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    another_manager = make_user(UserRole.MANAGER, system_user_id)

    substation_id = uuid4()
    department_id = uuid4()

    manager.enterprise_id = department_id
    another_manager.enterprise_id = department_id

    substation = Substation(
        id=substation_id,
        enterprise_id=department_id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    user_repository.users[manager.id] = manager
    user_repository.users[another_manager.id] = another_manager
    substation_repository.substations[substation_id] = substation

    task = await service.create(
        substation_id=substation_id,
        actor_id=manager.id,
    )

    # Manager назначает задачу самому себе.
    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=manager.id,
    )

    await service.accept(
        task.id,
        actor_id=manager.id,
    )

    await service.complete(
        task.id,
        actor_id=manager.id,
        inspection_date=date(2026, 9, 14),
        remarks="Осмотр выполнен.",
    )

    await service.send_to_review(
        task.id,
        actor_id=manager.id,
    )

    with pytest.raises(
        ValueError,
        match="не может проверять собственный результат",
    ):
        await service.review(
            task.id,
            actor_id=manager.id,
            approve=True,
        )

    # Другой Manager того же ПО должен иметь возможность проверить.
    result = await service.review(
        task.id,
        actor_id=another_manager.id,
        approve=True,
    )

    assert result.status == TaskStatus.CLOSED



@pytest.mark.asyncio
async def test_can_review_returns_true_for_manager_from_same_department(
    service_dependencies,
    system_user_id,
):
    service, repository, user_repository, substation_repository = (
        service_dependencies
    )

    department_id = uuid4()
    substation_id = uuid4()
    manager = make_user(UserRole.MANAGER, system_user_id)
    manager.enterprise_id = department_id

    task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.UNDER_REVIEW,
        assigned_to=uuid4(),
        substation_id=substation_id,
    )
    substation = SimpleNamespace(
        id=substation_id,
        enterprise_id=department_id,
    )

    repository.tasks[task.id] = task
    user_repository.users[manager.id] = manager
    substation_repository.substations[substation_id] = substation

    assert await service.can_review(
        task.id,
        actor_id=manager.id,
    ) is True


@pytest.mark.asyncio
async def test_can_review_returns_false_for_own_inspection(
    service_dependencies,
    system_user_id,
):
    service, repository, user_repository, substation_repository = (
        service_dependencies
    )

    department_id = uuid4()
    substation_id = uuid4()
    manager = make_user(UserRole.MANAGER, system_user_id)
    manager.enterprise_id = department_id

    task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.UNDER_REVIEW,
        assigned_to=manager.id,
        substation_id=substation_id,
    )

    repository.tasks[task.id] = task
    user_repository.users[manager.id] = manager
    substation_repository.substations[substation_id] = SimpleNamespace(
        id=substation_id,
        enterprise_id=department_id,
    )

    assert await service.can_review(
        task.id,
        actor_id=manager.id,
    ) is False


@pytest.mark.asyncio
async def test_can_review_returns_false_for_another_department(
    service_dependencies,
    system_user_id,
):
    service, repository, user_repository, substation_repository = (
        service_dependencies
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    manager.enterprise_id = uuid4()
    substation_id = uuid4()

    task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.UNDER_REVIEW,
        assigned_to=uuid4(),
        substation_id=substation_id,
    )

    repository.tasks[task.id] = task
    user_repository.users[manager.id] = manager
    substation_repository.substations[substation_id] = SimpleNamespace(
        id=substation_id,
        enterprise_id=uuid4(),
    )

    assert await service.can_review(
        task.id,
        actor_id=manager.id,
    ) is False


@pytest.mark.asyncio
async def test_can_review_returns_false_for_non_manager(
    service_dependencies,
    system_user_id,
):
    service, repository, user_repository, substation_repository = (
        service_dependencies
    )

    engineer = make_user(UserRole.ENGINEER, system_user_id)
    substation_id = uuid4()
    task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.UNDER_REVIEW,
        assigned_to=uuid4(),
        substation_id=substation_id,
    )

    repository.tasks[task.id] = task
    user_repository.users[engineer.id] = engineer
    substation_repository.substations[substation_id] = SimpleNamespace(
        id=substation_id,
        enterprise_id=engineer.enterprise_id,
    )

    assert await service.can_review(
        task.id,
        actor_id=engineer.id,
    ) is False


@pytest.mark.asyncio
async def test_can_review_returns_false_when_task_is_not_under_review(
    service_dependencies,
    system_user_id,
):
    service, repository, user_repository, substation_repository = (
        service_dependencies
    )

    manager = make_user(UserRole.MANAGER, system_user_id)
    task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.IN_PROGRESS,
        assigned_to=uuid4(),
        substation_id=uuid4(),
    )

    repository.tasks[task.id] = task
    user_repository.users[manager.id] = manager

    assert await service.can_review(
        task.id,
        actor_id=manager.id,
    ) is False


@pytest.mark.asyncio
async def test_can_review_returns_false_when_task_does_not_exist(
    service_dependencies,
    system_user_id,
):
    service, _, user_repository, _ = service_dependencies
    manager = make_user(UserRole.MANAGER, system_user_id)
    user_repository.users[manager.id] = manager

    assert await service.can_review(
        uuid4(),
        actor_id=manager.id,
    ) is False
