from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from uuid6 import uuid7

from app.application.tasks.service import TaskService
from app.domain.enums import (
    DocumentStatus,
    MaintenanceType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.maintenance import TORecord
from app.domain.otd import OTDVersion
from app.domain.program import Program, ProgramType
from app.domain.schema import SchemaRecord
from app.domain.settings_record import SettingsRecord
from app.domain.task import Task
from app.domain.task_history import TaskHistory


class FakeTaskRepository:
    """Минимальный repository для тестирования бизнес-логики без PostgreSQL."""

    def __init__(self) -> None:
        self.tasks = []
        self.history = []
        self.session = self
        self.otd_versions = []
        self.settings_records = []
        self.schema_records = []
        self.programs = []
        self.to_records = []
        self.substation_instruction_versions = {}

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

    async def refresh_for_mutation(self, task):
        return task

    async def get_otd_version_by_task_id(self, task_id):
        """Возвращает версию ОТД, связанную с указанной задачей."""
        return next(
            (version for version in self.otd_versions if version.task_id == task_id),
            None,
        )

    async def get_settings_record_by_task_id(self, task_id):
        """Возвращает запись уставок, связанную с указанной задачей."""
        return next(
            (record for record in self.settings_records if record.task_id == task_id),
            None,
        )

    async def get_schema_record_by_task_id(self, task_id):
        """Возвращает запись схем, связанную с указанной задачей."""
        return next(
            (
                record
                for record in self.schema_records
                if record.task_id == task_id
                and getattr(record, "deleted_at", None) is None
            ),
            None,
        )

    async def get_program_by_task_id(self, task_id):
        """Возвращает программу, связанную с указанной задачей."""
        return next(
            (program for program in self.programs if program.task_id == task_id),
            None,
        )

    async def get_to_record_by_task_id(self, task_id):
        """Возвращает запись ТО, связанную с указанной задачей."""
        return next(
            (record for record in self.to_records if record.task_id == task_id),
            None,
        )

    async def get_substation_instruction_version_by_task_id(self, task_id):
        return self.substation_instruction_versions.get(task_id)

    async def get_assignment_actor(
        self,
        *,
        task_id,
        assignee_id,
    ):
        """Возвращает автора последнего назначения текущего исполнителя."""
        assignment_events = [
            history
            for history in self.history
            if history.task_id == task_id
            and history.event_type in {"assigned", "reassigned"}
        ]

        if not assignment_events:
            return None

        # История в fake-репозитории добавляется в хронологическом порядке.
        latest_assignment = assignment_events[-1]

        # При переназначении проверяем, что последним назначен
        # именно тот исполнитель, который сейчас отклоняет задачу.
        if (
            latest_assignment.event_type == "reassigned"
            and latest_assignment.new_assignee_id != assignee_id
        ):
            return None

        return latest_assignment.actor_id


class FakeNotificationService:
    """Собирает вызовы создания уведомлений для проверки TaskService."""

    def __init__(self) -> None:
        self.calls = []

    async def create_for_history(
        self,
        *,
        history,
        recipient_ids,
    ):
        recipients = list(recipient_ids)
        self.calls.append(
            {
                "history": history,
                "recipient_ids": recipients,
            }
        )
        return []


class FakeUserRepository:
    def __init__(self) -> None:
        self.users = {}
        self.engineers_by_enterprise = {}
        self.requested_enterprise_ids = []

    async def get_by_id(self, user_id):
        return self.users.get(user_id)

    async def get_active_engineers_by_enterprise(self, enterprise_id):
        self.requested_enterprise_ids.append(enterprise_id)
        return self.engineers_by_enterprise.get(enterprise_id, [])


class FakeURZARepository:
    def __init__(self) -> None:
        self.urzas = {}

    async def get_by_id(self, urza_id):
        if urza_id not in self.urzas:
            self.urzas[urza_id] = SimpleNamespace(
                id=urza_id,
                deleted_at=None,
                connection=SimpleNamespace(
                    substation=SimpleNamespace(
                        enterprise_id=uuid4(),
                    ),
                ),
            )
        return self.urzas[urza_id]

    async def lock_active_by_id(self, urza_id):
        urza = await self.get_by_id(urza_id)
        return urza is not None and getattr(urza, "deleted_at", None) is None


class FakeSubstationRepository:
    async def get_by_id(self, substation_id):
        return SimpleNamespace(id=substation_id, deleted_at=None)

    async def lock_active_by_id(self, substation_id):
        substation = await self.get_by_id(substation_id)
        return substation is not None and substation.deleted_at is None


class FakeAccessService:
    def __init__(self) -> None:
        self.user_repository = FakeUserRepository()
        self.urza_repository = FakeURZARepository()
        self.substation_repository = FakeSubstationRepository()
        self.access = {}
        self.substation_access = {}

    async def can_access_urza(self, user_id, urza_id):
        return self.access.get((user_id, urza_id), True)

    async def can_access_substation(self, user_id, substation_id):
        return self.substation_access.get((user_id, substation_id), True)

    async def can_modify_urza(self, user_id, urza_id):
        return await self.can_access_urza(user_id, urza_id)

    async def can_modify_substation(self, user_id, substation_id):
        return await self.can_access_substation(user_id, substation_id)


class FakeURZAInstructionRepository:
    """Минимальный fake для проверки наличия инструкции и её версии."""

    def __init__(self) -> None:
        self.instructions = {}
        self.latest_working_versions = {}
        self.calls = []

    async def get_by_urza_id(self, urza_id):
        self.calls.append(("get_by_urza_id", urza_id))
        return self.instructions.get(urza_id)

    async def get_latest_working_version(self, instruction_id):
        self.calls.append(("get_latest_working_version", instruction_id))
        return self.latest_working_versions.get(instruction_id)


@pytest.mark.asyncio
async def test_only_substation_instruction_tasks_offer_create_result():
    actor_id = uuid7()
    repository = FakeTaskRepository()
    service = make_task_service(repository, FakeAccessService())
    urza_task = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        substation_id=None,
        work_type=TaskWorkType.INSTRUCTION,
        assigned_to=actor_id,
        status=TaskStatus.IN_PROGRESS,
        deleted_at=None,
    )
    substation_task = SimpleNamespace(
        id=uuid7(),
        urza_id=None,
        substation_id=uuid7(),
        work_type=TaskWorkType.INSTRUCTION,
        assigned_to=actor_id,
        status=TaskStatus.IN_PROGRESS,
        deleted_at=None,
    )

    urza_actions = await service.get_available_actions(
        task=urza_task,
        actor_id=actor_id,
    )
    substation_actions = await service.get_available_actions(
        task=substation_task,
        actor_id=actor_id,
    )

    assert urza_actions == {"complete_task"}
    assert substation_actions == {"complete_task", "create_result"}


def make_task_service(
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
    instruction_repository: FakeURZAInstructionRepository | None = None,
    notification_service: FakeNotificationService | None = None,
) -> TaskService:
    return TaskService(
        task_repository=repository,
        access_service=access_service,
        urza_instruction_repository=(
            instruction_repository or FakeURZAInstructionRepository()
        ),
        notification_service=(
            notification_service or FakeNotificationService()
        ),
    )


@pytest.mark.asyncio
async def test_task_mutation_rejects_archived_object_without_changing_status() -> None:
    repository = FakeTaskRepository()
    access_service = FakeAccessService()
    service = make_task_service(repository, access_service)
    actor_id, urza_id = uuid4(), uuid4()
    access_service.access[(actor_id, urza_id)] = False
    task = SimpleNamespace(
        id=uuid4(),
        urza_id=urza_id,
        substation_id=None,
        assigned_to=actor_id,
        deleted_at=None,
        status=TaskStatus.ASSIGNED,
    )

    with pytest.raises(PermissionError, match="архивного объекта"):
        await service.accept_task(task=task, actor_id=actor_id)

    assert task.status is TaskStatus.ASSIGNED


@pytest.mark.asyncio
async def test_task_owner_is_locked_before_task_is_refreshed() -> None:
    calls = []

    class LockingURZARepository(FakeURZARepository):
        async def lock_active_by_id(self, urza_id):
            calls.append(("owner_lock", urza_id))
            return True

    class RefreshingTaskRepository(FakeTaskRepository):
        async def refresh_for_mutation(self, task):
            calls.append(("task_refresh", task.id))
            return task

    repository = RefreshingTaskRepository()
    access_service = FakeAccessService()
    access_service.urza_repository = LockingURZARepository()
    service = make_task_service(repository, access_service)
    task = SimpleNamespace(
        id=uuid4(), urza_id=uuid4(), substation_id=None, deleted_at=None
    )

    await service._lock_task_owner(task)

    assert calls == [
        ("owner_lock", task.urza_id),
        ("task_refresh", task.id),
    ]


@pytest.mark.asyncio
async def test_reassign_executor_locks_current_owner_before_mutation() -> None:
    calls = []
    repository = FakeTaskRepository()
    access_service = FakeAccessService()
    urza_id = uuid4()
    manager_id = uuid4()
    previous_assignee_id = uuid4()
    new_assignee_id = uuid4()
    enterprise_id = uuid4()

    class RecordingURZARepository(FakeURZARepository):
        async def lock_active_by_id(self, owner_id):
            calls.append(("owner_lock", owner_id))
            return True

    class RecordingTaskRepository(FakeTaskRepository):
        async def refresh_for_mutation(self, task):
            calls.append(("task_refresh", task.id))
            return task

    repository = RecordingTaskRepository()
    access_service.urza_repository = RecordingURZARepository()
    access_service.urza_repository.urzas[urza_id] = SimpleNamespace(
        deleted_at=None,
        connection=SimpleNamespace(
            substation=SimpleNamespace(enterprise_id=enterprise_id),
        ),
    )
    access_service.user_repository.users[manager_id] = SimpleNamespace(
        id=manager_id,
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
    )
    engineer = SimpleNamespace(
        id=new_assignee_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    access_service.user_repository.engineers_by_enterprise[enterprise_id] = [
        engineer,
    ]
    task = SimpleNamespace(
        id=uuid4(),
        urza_id=urza_id,
        substation_id=None,
        assigned_to=previous_assignee_id,
        status=TaskStatus.ASSIGNED,
        deleted_at=None,
        deadline_at=datetime(2026, 9, 20, 10, 0),
    )
    service = make_task_service(repository, access_service)

    await service.reassign_task(
        task=task,
        assigned_to=new_assignee_id,
        actor_id=manager_id,
        assigned_at=datetime(2026, 9, 14, 9, 30),
    )

    assert calls == [
        ("owner_lock", urza_id),
        ("task_refresh", task.id),
    ]
    assert task.assigned_to == new_assignee_id
    assert repository.history[-1].previous_assignee_id == previous_assignee_id
    assert repository.history[-1].new_assignee_id == new_assignee_id


def make_task_service_with_active_assignee(
    repository: FakeTaskRepository,
    actor_id,
    instruction_repository: FakeURZAInstructionRepository | None = None,
) -> TaskService:
    """Создаёт сервис с зарегистрированным активным исполнителем задачи."""
    access_service = FakeAccessService()
    access_service.user_repository.users[actor_id] = SimpleNamespace(
        id=actor_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    return make_task_service(repository, access_service, instruction_repository)


def configure_available_assignee(
    service: TaskService,
    *,
    urza_id,
    engineer_id,
) -> None:
    """Подготавливает URZA и доступного исполнителя для теста."""
    enterprise_id = uuid7()

    service.access_service.urza_repository.urzas[urza_id] = (
        SimpleNamespace(
            deleted_at=None,
            connection=SimpleNamespace(
                substation=SimpleNamespace(
                    enterprise_id=enterprise_id,
                ),
            ),
        )
    )

    service.access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    service.access_service.user_repository.engineers_by_enterprise[
        enterprise_id
    ] = [
        SimpleNamespace(
            id=engineer_id,
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
    ]


@pytest.fixture
def repository() -> FakeTaskRepository:
    return FakeTaskRepository()


@pytest.fixture
def access_service() -> FakeAccessService:
    return FakeAccessService()


@pytest.fixture
def service(
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
    system_user_id,
) -> TaskService:
    access_service.user_repository.users[system_user_id] = SimpleNamespace(
        id=system_user_id,
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
    )
    return make_task_service(repository, access_service)


@pytest.mark.asyncio
async def test_create_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    now = datetime(2026, 9, 13, 10, 0)

    urza_id = uuid4()
    created_by = system_user_id

    task = await service.create_task(
        urza_id=urza_id,
        work_type=TaskWorkType.OTD,
        created_by=created_by,
        now=now,
    )

    assert task.urza_id == urza_id
    assert task.work_type == TaskWorkType.OTD
    assert task.created_by == created_by
    assert task.updated_by == created_by
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
@pytest.mark.parametrize(
    ("role", "active", "deleted_at", "has_access", "expected"),
    [
        (UserRole.MANAGER, True, None, True, True),
        (UserRole.SUPERADMIN, True, None, True, True),
        (UserRole.ADMIN, True, None, True, False),
        (UserRole.ENGINEER, True, None, True, False),
        (UserRole.MANAGER, False, None, True, False),
        (UserRole.MANAGER, True, datetime(2026, 1, 1), True, False),
        (UserRole.MANAGER, True, None, False, False),
    ],
)
async def test_can_issue_task_checks_role_activity_and_urza_access(
    service: TaskService,
    access_service: FakeAccessService,
    role: UserRole,
    active: bool,
    deleted_at: datetime | None,
    has_access: bool,
    expected: bool,
) -> None:
    actor_id = uuid7()
    urza_id = uuid7()
    access_service.user_repository.users[actor_id] = SimpleNamespace(
        id=actor_id,
        role=role,
        active=active,
        deleted_at=deleted_at,
    )
    access_service.access[(actor_id, urza_id)] = has_access

    assert await service.can_issue_task(actor_id=actor_id, urza_id=urza_id) is expected


@pytest.mark.asyncio
async def test_cannot_issue_task_for_archived_urza() -> None:
    actor_id = uuid7()
    urza_id = uuid7()

    class _UserRepository:
        async def get_by_id(self, _user_id):
            return SimpleNamespace(
                id=actor_id, role=UserRole.MANAGER, active=True, deleted_at=None,
            )

    class _URZARepository:
        async def get_by_id(self, _urza_id):
            return SimpleNamespace(deleted_at=datetime(2026, 1, 1))

    class _Access:
        user_repository = _UserRepository()
        urza_repository = _URZARepository()

        async def can_access_urza(self, _user_id, _urza_id):
            return True

    FakeTaskRepository
    service = TaskService(
        task_repository=SimpleNamespace(),
        access_service=_Access(),
        urza_instruction_repository=SimpleNamespace(),
        notification_service=FakeNotificationService(),
    )

    assert not await service.can_issue_task(actor_id=actor_id, urza_id=urza_id)


@pytest.mark.asyncio
async def test_accessible_manager_can_create_task(
    service: TaskService,
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
    system_user_id,
) -> None:
    urza_id = uuid7()
    access_service.access[(system_user_id, urza_id)] = True

    task = await service.create_task(
        urza_id=urza_id,
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    assert task in repository.tasks
    assert task.urza_id == urza_id
    assert task.status is TaskStatus.CREATED
    assert repository.history[-1].actor_id == system_user_id


@pytest.mark.asyncio
async def test_user_without_issue_permission_cannot_create_task(
    service: TaskService,
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
) -> None:
    actor_id = uuid7()
    urza_id = uuid7()
    access_service.user_repository.users[actor_id] = SimpleNamespace(
        id=actor_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    access_service.access[(actor_id, urza_id)] = True

    with pytest.raises(PermissionError, match="не может выдавать задания"):
        await service.create_task(
            urza_id=urza_id,
            work_type=TaskWorkType.OTD,
            created_by=actor_id,
        )

    assert repository.tasks == []
    assert repository.history == []


@pytest.mark.asyncio
async def test_manager_with_urza_access_gets_available_assignees(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    manager_id = uuid7()
    urza_id = uuid7()
    enterprise_id = uuid7()
    engineers = [
        SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER),
        SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER),
    ]
    access_service.user_repository.users[manager_id] = SimpleNamespace(
        id=manager_id,
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
    )
    access_service.access[(manager_id, urza_id)] = True
    access_service.urza_repository.urzas[urza_id] = SimpleNamespace(
        deleted_at=None,
        connection=SimpleNamespace(
            substation=SimpleNamespace(enterprise_id=enterprise_id),
        ),
    )
    access_service.user_repository.engineers_by_enterprise[enterprise_id] = engineers

    result = await service.get_available_assignees(
        actor_id=manager_id,
        urza_id=urza_id,
    )

    assert result == engineers
    assert access_service.user_repository.requested_enterprise_ids == [enterprise_id]


@pytest.mark.asyncio
async def test_manager_without_urza_access_cannot_get_available_assignees(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    manager_id = uuid7()
    urza_id = uuid7()
    access_service.user_repository.users[manager_id] = SimpleNamespace(
        id=manager_id,
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
    )
    access_service.access[(manager_id, urza_id)] = False

    with pytest.raises(PermissionError, match="не может выдавать задания"):
        await service.get_available_assignees(actor_id=manager_id, urza_id=urza_id)

    assert access_service.user_repository.requested_enterprise_ids == []


@pytest.mark.asyncio
async def test_engineer_cannot_get_available_assignees(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    engineer_id = uuid7()
    urza_id = uuid7()
    access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    access_service.access[(engineer_id, urza_id)] = True

    with pytest.raises(PermissionError, match="не может выдавать задания"):
        await service.get_available_assignees(actor_id=engineer_id, urza_id=urza_id)

    assert access_service.user_repository.requested_enterprise_ids == []


@pytest.mark.asyncio
async def test_missing_urza_after_issue_permission_raises_value_error(
    access_service: FakeAccessService,
) -> None:
    service = make_task_service(FakeTaskRepository(), access_service)
    manager_id = uuid7()
    urza_id = uuid7()
    access_service.urza_repository.urzas[urza_id] = None
    access_service.urza_repository.urzas[urza_id] = None
    access_service.user_repository.users[manager_id] = SimpleNamespace(
        id=manager_id,
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
    )
    access_service.access[(manager_id, urza_id)] = True

    with pytest.raises(PermissionError, match="не может выдавать задания"):
        await service.get_available_assignees(actor_id=manager_id, urza_id=urza_id)

    assert access_service.user_repository.requested_enterprise_ids == []


@pytest.mark.asyncio
async def test_create_maintenance_task_requires_maintenance_type(
    service: TaskService, system_user_id
) -> None:
    with pytest.raises(ValueError, match="maintenance_type"):
        await service.create_task(
            urza_id=uuid4(),
            work_type=TaskWorkType.MAINTENANCE,
            created_by=system_user_id,
        )


@pytest.mark.asyncio
async def test_available_actions_match_task_state_and_reviewer_access(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    manager_id = uuid7()
    executor_id = uuid7()
    other_user_id = uuid7()
    urza_id = uuid7()

    manager = SimpleNamespace(
        id=manager_id,
        active=True,
        deleted_at=None,
        role=UserRole.MANAGER,
    )
    access_service.user_repository.users[manager_id] = manager
    access_service.access[(manager_id, urza_id)] = True

    # Исполнитель может принять назначенное ему задание
    # или отказаться от него с указанием причины.
    assigned = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        assigned_to=executor_id,
        status=TaskStatus.ASSIGNED,
        deleted_at=None,
    )

    # Исполнитель может завершить работу по своему заданию.
    in_progress = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        assigned_to=executor_id,
        status=TaskStatus.IN_PROGRESS,
        deleted_at=None,
    )

    # Исполнитель может передать завершённое задание на проверку.
    completed = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        assigned_to=executor_id,
        status=TaskStatus.COMPLETED,
        deleted_at=None,
    )

    # Руководитель с доступом к объекту может проверить задание.
    under_review = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        assigned_to=executor_id,
        status=TaskStatus.UNDER_REVIEW,
        deleted_at=None,
    )

    # Чужое назначенное задание недоступно исполнителю.
    assigned_to_other = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        assigned_to=other_user_id,
        status=TaskStatus.ASSIGNED,
        deleted_at=None,
    )

    assert await service.get_available_actions(
        task=assigned,
        actor_id=executor_id,
    ) == {"accept_task", "reject_task"}

    assert await service.get_available_actions(
        task=in_progress,
        actor_id=executor_id,
    ) == {"complete_task"}

    assert await service.get_available_actions(
        task=completed,
        actor_id=executor_id,
    ) == {"submit_for_review"}

    assert await service.get_available_actions(
        task=under_review,
        actor_id=manager_id,
    ) == {"close_task", "return_for_revision"}

    assert await service.get_available_actions(
        task=assigned_to_other,
        actor_id=executor_id,
    ) == set()


@pytest.mark.asyncio
async def test_available_review_actions_are_hidden_for_non_reviewer(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    engineer_id = uuid7()
    urza_id = uuid7()
    access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id,
        active=True,
        deleted_at=None,
        role=UserRole.ENGINEER,
    )
    task = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=TaskStatus.UNDER_REVIEW,
        deleted_at=None,
    )

    assert await service.get_available_actions(
        task=task,
        actor_id=engineer_id,
    ) == set()


@pytest.mark.asyncio
async def test_assigned_engineer_can_open_maintenance_result_form(service):
    engineer_id = uuid7()
    task = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        work_type=TaskWorkType.MAINTENANCE,
        deleted_at=None,
    )

    assert await service.get_available_actions(
        task=task,
        actor_id=engineer_id,
    ) == {"complete_task", "create_result"}


@pytest.mark.asyncio
async def test_non_maintenance_task_cannot_have_maintenance_type(
    service: TaskService, system_user_id
) -> None:
    with pytest.raises(ValueError, match="maintenance_type"):
        await service.create_task(
            urza_id=uuid4(),
            work_type=TaskWorkType.OTD,
            created_by=system_user_id,
            maintenance_type=MaintenanceType.V,
        )


@pytest.mark.asyncio
async def test_create_maintenance_task(service: TaskService, system_user_id) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        created_by=system_user_id,
        maintenance_type=MaintenanceType.K1,
    )

    assert task.work_type == TaskWorkType.MAINTENANCE
    assert task.maintenance_type == MaintenanceType.K1


@pytest.mark.asyncio
async def test_assign_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 14, 15, 30)



    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=created_at,
    )

    assigned_to = uuid4()

    original_deadline = task.deadline_at
    assigned_to = uuid4()
    actor_id = system_user_id

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=assigned_to,
    )

    await service.assign_task(
        task=task,
        assigned_to=assigned_to,
        actor_id=actor_id,
        assigned_at=assigned_at,
    )

    assert task.status == TaskStatus.ASSIGNED
    assert task.updated_by == actor_id
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
    notification_calls = service.notification_service.calls
    assert len(notification_calls) == 1
    assert notification_calls[0]["history"] is history
    assert notification_calls[0]["recipient_ids"] == [assigned_to]


@pytest.mark.asyncio
async def test_assign_task_rejects_invalid_status(
    service: TaskService,
    system_user_id,
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=datetime(2026, 9, 13, 10, 0),
    )

    assigned_to = uuid4()

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=assigned_to,
    )

    await service.assign_task(
        task=task,
        assigned_to=assigned_to,
        actor_id=system_user_id,
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.assign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=system_user_id,
            assigned_at=datetime(2026, 9, 13, 13, 0),
        )


@pytest.mark.asyncio
async def test_accept_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    accepted_at = datetime(2026, 9, 14, 9, 30)

    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=created_at,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
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
    service: TaskService, system_user_id
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=datetime(2026, 9, 13, 10, 0),
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    with pytest.raises(ValueError, match="назначенный инженер"):
        await service.accept_task(
            task=task,
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_accept_task_rejects_invalid_status(
    service: TaskService, system_user_id
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=datetime(2026, 9, 13, 10, 0),
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
        assigned_at=datetime(2026, 9, 13, 12, 0),
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    assert task.updated_by == engineer_id

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.accept_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_reject_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    rejected_at = datetime(2026, 9, 14, 9, 30)

    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=created_at,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
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
    assert task.updated_by == engineer_id
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
    notification_calls = service.notification_service.calls
    assert len(notification_calls) == 2

    rejection_notification = notification_calls[-1]
    assert rejection_notification["history"] is history
    assert rejection_notification["recipient_ids"] == [system_user_id]


@pytest.mark.asyncio
async def test_reject_task_does_not_notify_when_assignment_actor_not_found(
    service: TaskService,
    repository: FakeTaskRepository,
    system_user_id,
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    # Имитируем назначенное задание без истории назначения.
    task.status = TaskStatus.ASSIGNED
    task.assigned_to = engineer_id

    await service.reject_task(
        task=task,
        actor_id=engineer_id,
        reason="Не могу выполнить задание.",
    )

    assert task.status is TaskStatus.REJECTED
    assert repository.history[-1].event_type == "rejected"
    assert service.notification_service.calls == []


@pytest.mark.asyncio
async def test_reject_task_requires_reason(
    service: TaskService, system_user_id
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    with pytest.raises(ValueError, match="Причина обязательна"):
        await service.reject_task(
            task=task,
            actor_id=engineer_id,
            reason="   ",
        )


@pytest.mark.asyncio
async def test_reject_task_only_by_assigned_engineer(
    service: TaskService, system_user_id
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    with pytest.raises(ValueError, match="назначенный инженер"):
        await service.reject_task(
            task=task,
            actor_id=uuid4(),
            reason="Нет возможности выполнить.",
        )


@pytest.mark.asyncio
async def test_reassign_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    first_assigned_at = datetime(2026, 9, 13, 12, 0)
    reassigned_at = datetime(2026, 9, 14, 9, 30)

    first_engineer_id = uuid4()
    second_engineer_id = uuid4()
    manager_id = system_user_id

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=created_at,
    )

    enterprise_id = uuid7()

    service.access_service.urza_repository.urzas[task.urza_id] = (
        SimpleNamespace(
            deleted_at=None,
            connection=SimpleNamespace(
                substation=SimpleNamespace(
                    enterprise_id=enterprise_id,
                ),
            ),
        )
    )

    service.access_service.user_repository.engineers_by_enterprise[
        enterprise_id
    ] = [
        SimpleNamespace(
            id=first_engineer_id,
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
        SimpleNamespace(
            id=second_engineer_id,
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
    ]

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
    assert history.previous_assignee_id == first_engineer_id
    assert history.new_assignee_id == second_engineer_id
    assert history.old_status == TaskStatus.ASSIGNED
    assert history.new_status == TaskStatus.ASSIGNED
    assert history.actor_id == manager_id
    assert history.created_at == reassigned_at

    notification_calls = service.notification_service.calls
    assert len(notification_calls) == 2

    reassignment_notification = notification_calls[-1]
    assert reassignment_notification["history"] is history
    assert reassignment_notification["recipient_ids"] == [
        first_engineer_id,
        second_engineer_id,
    ]


@pytest.mark.asyncio
async def test_repeated_reassignments_keep_each_pair_of_assignees(
    service: TaskService,
    repository: FakeTaskRepository,
    system_user_id,
) -> None:
    initial_assignee_id = uuid4()
    second_assignee_id = uuid4()
    third_assignee_id = uuid4()
    urza_id = uuid4()
    enterprise_id = uuid7()

    service.access_service.urza_repository.urzas[urza_id] = SimpleNamespace(
        deleted_at=None,
        connection=SimpleNamespace(
            substation=SimpleNamespace(enterprise_id=enterprise_id),
        ),
    )
    service.access_service.user_repository.engineers_by_enterprise[
        enterprise_id
    ] = [
        SimpleNamespace(id=user_id, role=UserRole.ENGINEER, active=True, deleted_at=None)
        for user_id in (
            initial_assignee_id,
            second_assignee_id,
            third_assignee_id,
        )
    ]

    task = await service.create_task(
        urza_id=urza_id,
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )
    await service.assign_task(
        task=task,
        assigned_to=initial_assignee_id,
        actor_id=system_user_id,
    )
    await service.reassign_task(
        task=task,
        assigned_to=second_assignee_id,
        actor_id=system_user_id,
    )
    await service.reassign_task(
        task=task,
        assigned_to=third_assignee_id,
        actor_id=system_user_id,
    )

    reassignment_events = [
        event for event in repository.history if event.event_type == "reassigned"
    ]
    assert len(reassignment_events) == 2
    assert [
        (event.previous_assignee_id, event.new_assignee_id)
        for event in reassignment_events
    ] == [
        (initial_assignee_id, second_assignee_id),
        (second_assignee_id, third_assignee_id),
    ]

    assigned_event = next(
        event for event in repository.history if event.event_type == "assigned"
    )

    assignment_actor = await repository.get_assignment_actor(
        task_id=task.id,
        assignee_id=third_assignee_id,
    )
    assert assignment_actor == system_user_id

    wrong_assignee_actor = await repository.get_assignment_actor(
        task_id=task.id,
        assignee_id=initial_assignee_id,
    )
    assert wrong_assignee_actor is None
    assert assigned_event.previous_assignee_id is None
    assert assigned_event.new_assignee_id is None


@pytest.mark.asyncio
async def test_reassign_task_only_in_assigned_status(
    service: TaskService, system_user_id
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    with pytest.raises(ValueError, match="назначенную задачу"):
        await service.reassign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_reassign_task_requires_new_assignee(
    service: TaskService, system_user_id
) -> None:
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    with pytest.raises(ValueError, match="отличаться"):
        await service.reassign_task(
            task=task,
            assigned_to=engineer_id,
            actor_id=system_user_id,
        )



@pytest.mark.asyncio
async def test_reassign_task_rejects_unavailable_assignee_without_mutation(
    service: TaskService,
    repository: FakeTaskRepository,
    system_user_id,
) -> None:
    engineer_id = uuid4()
    unavailable_engineer_id = uuid4()
    assigned_at = datetime(2026, 9, 13, 12, 0)

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=datetime(2026, 9, 13, 10, 0),
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
        assigned_at=assigned_at,
    )

    original_assigned_to = task.assigned_to
    original_assigned_at = task.assigned_at
    original_acceptance_deadline_at = task.acceptance_deadline_at
    original_deadline_at = task.deadline_at
    original_updated_by = task.updated_by
    original_status = task.status
    original_history_count = len(repository.history)

    with pytest.raises(ValueError, match="доступным"):
        await service.reassign_task(
            task=task,
            assigned_to=unavailable_engineer_id,
            actor_id=system_user_id,
            assigned_at=datetime(2026, 9, 14, 9, 30),
        )

    assert task.assigned_to == original_assigned_to
    assert task.assigned_at == original_assigned_at
    assert task.acceptance_deadline_at == original_acceptance_deadline_at
    assert task.deadline_at == original_deadline_at
    assert task.updated_by == original_updated_by
    assert task.status is original_status
    assert len(repository.history) == original_history_count



@pytest.mark.asyncio
async def test_reassign_task_rejects_unauthorized_actor_without_mutation(
    service: TaskService,
    repository: FakeTaskRepository,
    system_user_id,
) -> None:
    engineer_id = uuid4()
    unauthorized_actor_id = uuid4()
    assigned_at = datetime(2026, 9, 13, 12, 0)

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=datetime(2026, 9, 13, 10, 0),
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
        assigned_at=assigned_at,
    )

    original_assigned_to = task.assigned_to
    original_assigned_at = task.assigned_at
    original_acceptance_deadline_at = task.acceptance_deadline_at
    original_deadline_at = task.deadline_at
    original_updated_by = task.updated_by
    original_status = task.status
    original_history_count = len(repository.history)

    with pytest.raises(PermissionError):
        await service.reassign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=unauthorized_actor_id,
            assigned_at=datetime(2026, 9, 14, 9, 30),
        )

    assert task.assigned_to == original_assigned_to
    assert task.assigned_at == original_assigned_at
    assert task.acceptance_deadline_at == original_acceptance_deadline_at
    assert task.deadline_at == original_deadline_at
    assert task.updated_by == original_updated_by
    assert task.status is original_status
    assert len(repository.history) == original_history_count



@pytest.mark.asyncio
async def test_complete_task(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    completed_at = datetime(2026, 9, 15, 14, 30)

    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
        now=created_at,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
        assigned_at=assigned_at,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    # Результат ОТД необходим для успешного завершения задачи.
    otd_version = OTDVersion(
        otd_id=uuid4(),
        version_number=1,
        effective_date=completed_at.date(),
        urza_service_life=10,
        urza_purpose="rza",
        task_id=task.id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    repository.otd_versions.append(otd_version)

    await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at == completed_at

    assert len(repository.history) == 5

    history = repository.history[4]

    assert history.task_id == task.id
    assert history.event_type == "completed"
    assert history.old_status == TaskStatus.IN_PROGRESS
    assert history.new_status == TaskStatus.COMPLETED
    assert history.actor_id == engineer_id
    assert history.created_at == completed_at
    # Завершение задания не создаёт дополнительного уведомления.
    assert len(service.notification_service.calls) == 1
    assert service.notification_service.calls[0]["history"].event_type == "assigned"


@pytest.mark.asyncio
async def test_complete_task_only_by_assigned_engineer(
    service: TaskService, system_user_id
) -> None:
    """Проверяет, что завершить задачу может только её исполнитель."""
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    with pytest.raises(ValueError, match="назначенный инженер"):
        await service.complete_task(
            task=task,
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_complete_task_rejects_invalid_status(
    service: TaskService, system_user_id
) -> None:
    """Проверяет, что завершение разрешено только для задачи в работе."""
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    engineer_id = uuid4()

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_otd_task_requires_otd_version(
    service: TaskService, system_user_id
) -> None:
    """Проверяет, что ОТД-задачу нельзя завершить без результата ОТД."""
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    with pytest.raises(ValueError, match="ОТД"):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_otd_task_with_otd_version(
    service: TaskService, repository: FakeTaskRepository, system_user_id
) -> None:
    """Проверяет завершение ОТД-задачи при наличии результата ОТД."""
    engineer_id = uuid4()
    completed_at = datetime(2026, 9, 15, 14, 30)

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    # Версия ОТД является результатом выполнения этой задачи.
    otd_version = OTDVersion(
        otd_id=uuid4(),
        version_number=1,
        effective_date=completed_at.date(),
        urza_service_life=10,
        urza_purpose="rza",
        task_id=task.id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    repository.otd_versions.append(otd_version)

    await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_settings_task_requires_settings_record(
    service: TaskService, system_user_id
) -> None:
    """Проверяет, что задачу по уставкам нельзя завершить без результата."""
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.SETTINGS,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.accept_task(
        task=task,
        actor_id=engineer_id,
    )

    with pytest.raises(ValueError, match="устав"):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_settings_task_with_result(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SETTINGS,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    settings_record = SettingsRecord(
        settings_form_id=uuid4(),
        change_date=datetime.now().date(),
        parameter_name="Ток срабатывания",
        initial_setting="5 A",
        new_setting="6 A",
        change_reason="Изменение уставки",
        created_by=engineer_id,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.settings_records.append(settings_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_schemes_task_requires_schema_record(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по схемам необходимо сохранить результат схем",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_schemes_task_with_scan_and_signed_form(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    schema_record = SchemaRecord(
        schema_form_id=uuid4(),
        schema_number="СХ-001",
        schema_name="Схема защиты линии",
        change_description="Изменение схемы",
        change_justification="Изменение оборудования",
        upload_date=datetime.now().date(),
        created_by=engineer_id,
        scan_file_id=uuid4(),
        editable_file_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.schema_records.append(schema_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_schemes_task_requires_signed_form(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    schema_record = SchemaRecord(
        schema_form_id=uuid4(),
        schema_number="СХ-001",
        schema_name="Схема защиты линии",
        change_description="Изменение схемы",
        change_justification="Изменение оборудования",
        upload_date=datetime.now().date(),
        created_by=engineer_id,
        scan_file_id=uuid4(),
        editable_file_id=None,
        signed_form_file_id=None,
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.schema_records.append(schema_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="подписан",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_schemes_task_requires_scan_or_editable_file(
    system_user_id,
) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    schema_record = SchemaRecord(
        schema_form_id=uuid4(),
        schema_number="СХ-001",
        schema_name="Схема защиты линии",
        change_description="Изменение схемы",
        change_justification="Изменение оборудования",
        upload_date=datetime.now().date(),
        created_by=engineer_id,
        scan_file_id=None,
        editable_file_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.schema_records.append(schema_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="скан или редактируемый файл",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_schemes_task_with_editable_and_signed_form(
    system_user_id,
) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    schema_record = SchemaRecord(
        schema_form_id=uuid4(),
        schema_number="СХ-002",
        schema_name="Схема автоматики",
        change_description="Изменение схемы",
        change_justification="Изменение оборудования",
        upload_date=datetime.now().date(),
        created_by=engineer_id,
        scan_file_id=None,
        editable_file_id=uuid4(),
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.schema_records.append(schema_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_program_task_requires_program(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по программе необходимо сохранить программу",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_program_task_with_scan(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    program = Program(
        urza_id=task.urza_id,
        program_type=ProgramType.COMMISSIONING,
        program_number="ПР-001",
        scan_file_id=uuid4(),
        editable_file_id=None,
        task_id=task.id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    repository.programs.append(program)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_to_record(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по ТО необходимо сохранить результат ТО",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_signed_form(system_user_id) -> None:
    engineer_id = uuid4()
    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )
    repository = FakeTaskRepository()
    repository.tasks.append(task)
    repository.to_records.append(
        TORecord(
            urza_id=task.urza_id,
            maintenance_date=datetime.now().date(),
            maintenance_type=MaintenanceType.K,
            created_by=engineer_id,
            scan_protocol_id=uuid4(),
            signed_form_file_id=None,
            task_id=task.id,
            updated_by=system_user_id,
        )
    )

    with pytest.raises(ValueError, match="скан подписанной формы"):
        await make_task_service_with_active_assignee(repository, engineer_id).complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_protocol(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    to_record = TORecord(
        urza_id=task.urza_id,
        maintenance_date=datetime.now().date(),
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        scan_protocol_id=None,
        editable_protocol_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.to_records.append(to_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="протокол",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_maintenance_task_without_protocol_for_tk(
    system_user_id,
) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.TK,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    to_record = TORecord(
        urza_id=task.urza_id,
        maintenance_date=datetime.now().date(),
        maintenance_type=MaintenanceType.TK,
        created_by=engineer_id,
        scan_protocol_id=None,
        editable_protocol_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.to_records.append(to_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "maintenance_type",
    [
        MaintenanceType.O,
        MaintenanceType.OSM,
    ],
)
async def test_complete_maintenance_task_without_protocol_for_non_protocol_types(
    maintenance_type: MaintenanceType, system_user_id
) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=maintenance_type,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    to_record = TORecord(
        urza_id=task.urza_id,
        maintenance_date=datetime.now().date(),
        maintenance_type=maintenance_type,
        created_by=engineer_id,
        scan_protocol_id=None,
        editable_protocol_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.to_records.append(to_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_maintenance_task_with_protocol(system_user_id) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    to_record = TORecord(
        urza_id=task.urza_id,
        maintenance_date=datetime.now().date(),
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        scan_protocol_id=uuid4(),
        editable_protocol_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.to_records.append(to_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_matching_maintenance_type(
    system_user_id,
) -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
        updated_by=system_user_id,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    # Результат относится к другому виду ТО, чем сама задача.
    to_record = TORecord(
        urza_id=task.urza_id,
        maintenance_date=datetime.now().date(),
        maintenance_type=MaintenanceType.TK,
        created_by=engineer_id,
        scan_protocol_id=uuid4(),
        editable_protocol_id=None,
        signed_form_file_id=uuid4(),
        task_id=task.id,
        updated_by=system_user_id,
    )
    repository.to_records.append(to_record)

    service = make_task_service_with_active_assignee(repository, engineer_id)

    with pytest.raises(
        ValueError,
        match="Вид ТО в результате не соответствует виду ТО в задаче",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


def _review_task(status, *, work_type=TaskWorkType.SCHEMES):
    return Task(
        id=uuid7(),
        urza_id=uuid7(),
        work_type=work_type,
        created_by=uuid7(),
        assigned_to=uuid7(),
        status=status,
        updated_by=uuid7(),
    )


def _add_manager(access_service, manager_id, *, active=True, deleted_at=None):
    access_service.user_repository.users[manager_id] = SimpleNamespace(
        role=UserRole.MANAGER,
        active=active,
        deleted_at=deleted_at,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
async def test_assigned_executor_can_submit_completed_task_for_review(
    repository,
    access_service,
    role,
) -> None:
    task = _review_task(TaskStatus.COMPLETED, work_type=TaskWorkType.PROGRAM)
    executor_id = task.assigned_to
    access_service.user_repository.users[executor_id] = SimpleNamespace(
        role=role,
        active=True,
        deleted_at=None,
    )
    service = make_task_service(repository, access_service)

    result = await service.submit_for_review(
        task=task,
        actor_id=executor_id,
        comment="Результат готов",
    )

    assert result.status is TaskStatus.UNDER_REVIEW
    assert result.updated_by == executor_id
    history = repository.history[-1]
    assert history.event_type == "sent_to_review"
    assert history.old_status is TaskStatus.COMPLETED
    assert history.new_status is TaskStatus.UNDER_REVIEW
    assert history.actor_id == executor_id
    assert history.comment == "Результат готов"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
async def test_only_assigned_executor_can_submit_task_for_review(
    repository,
    access_service,
    role,
) -> None:
    task = _review_task(TaskStatus.COMPLETED, work_type=TaskWorkType.PROGRAM)
    actor_id = uuid7()
    access_service.user_repository.users[actor_id] = SimpleNamespace(
        role=role,
        active=True,
        deleted_at=None,
    )
    if role is UserRole.MANAGER:
        access_service.access[(actor_id, task.urza_id)] = True
    service = make_task_service(repository, access_service)

    with pytest.raises(ValueError, match="только назначенный исполнитель"):
        await service.submit_for_review(task=task, actor_id=actor_id)

    assert task.status is TaskStatus.COMPLETED
    assert repository.history == []


@pytest.mark.asyncio
async def test_deleted_task_cannot_be_submitted_for_review(
    repository,
    access_service,
) -> None:
    task = _review_task(TaskStatus.COMPLETED, work_type=TaskWorkType.PROGRAM)
    task.deleted_at = datetime.now()

    with pytest.raises(ValueError, match="удалённое задание"):
        await make_task_service(repository, access_service).submit_for_review(
            task=task,
            actor_id=task.assigned_to,
        )

    assert task.status is TaskStatus.COMPLETED
    assert repository.history == []


@pytest.mark.asyncio
async def test_available_actions_use_assignment_for_completed_task(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    task = _review_task(TaskStatus.COMPLETED, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    access_service.access[(manager_id, task.urza_id)] = True

    assert await service.get_available_actions(
        task=task,
        actor_id=task.assigned_to,
    ) == {"submit_for_review"}
    assert await service.get_available_actions(
        task=task,
        actor_id=manager_id,
    ) == set()


@pytest.mark.asyncio
async def test_available_reviewer_actions_still_require_manager_access(
    service: TaskService,
    access_service: FakeAccessService,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    access_service.access[(manager_id, task.urza_id)] = True

    assert await service.get_available_actions(
        task=task,
        actor_id=manager_id,
    ) == {"close_task", "return_for_revision"}
    access_service.access[(manager_id, task.urza_id)] = False
    assert await service.get_available_actions(
        task=task,
        actor_id=manager_id,
    ) == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "start", "target", "event_type"),
    [
        (
            "close_task",
            TaskStatus.UNDER_REVIEW,
            TaskStatus.CLOSED,
            "review_approved",
        ),
        (
            "return_for_revision",
            TaskStatus.UNDER_REVIEW,
            TaskStatus.IN_PROGRESS,
            "review_rejected",
        ),
    ],
)
async def test_accessible_manager_can_perform_review_transition(
    repository,
    access_service,
    system_user_id,
    method_name,
    start,
    target,
    event_type,
) -> None:
    task = _review_task(start, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    assert manager_id != task.created_by
    assert manager_id != task.assigned_to
    _add_manager(access_service, manager_id)
    access_service.access[(manager_id, task.urza_id)] = True
    service = make_task_service(repository, access_service)

    result = await getattr(service, method_name)(
        task=task,
        actor_id=manager_id,
        comment="Проверено",
    )

    assert result.status is target
    assert result.updated_by == manager_id
    if target is TaskStatus.CLOSED:
        assert result.closed_at is not None
    history = repository.history[-1]
    assert history.event_type == event_type
    assert history.old_status is start
    assert history.new_status is target
    assert history.actor_id == manager_id
    assert history.comment == "Проверено"


@pytest.mark.asyncio
@pytest.mark.parametrize("comment", [None, "", "   "])
async def test_return_for_revision_requires_reason(
    repository,
    access_service,
    system_user_id,
    comment,
) -> None:
    task = _review_task(
        TaskStatus.UNDER_REVIEW,
        work_type=TaskWorkType.PROGRAM,
    )
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    access_service.access[(manager_id, task.urza_id)] = True

    service = make_task_service(repository, access_service)

    with pytest.raises(ValueError, match="Причина обязательна"):
        await service.return_for_revision(
            task=task,
            actor_id=manager_id,
            comment=comment,
        )

    assert task.status is TaskStatus.UNDER_REVIEW
    assert repository.history == []


@pytest.mark.asyncio
async def test_revision_cycle_clears_previous_completion_and_records_new_date(
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
) -> None:
    engineer_id = uuid4()
    manager_id = uuid4()
    original_completion = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    new_completion = datetime(2026, 10, 13, 15, 30, tzinfo=UTC)
    task = _review_task(TaskStatus.COMPLETED, work_type=TaskWorkType.PROGRAM)
    task.assigned_to = engineer_id
    task.completed_at = original_completion
    original_completion_event = TaskHistory(
        task_id=task.id,
        event_type="completed",
        old_status=TaskStatus.IN_PROGRESS,
        new_status=TaskStatus.COMPLETED,
        actor_id=engineer_id,
        created_at=original_completion,
    )
    repository.history.append(original_completion_event)
    repository.programs.append(
        SimpleNamespace(task_id=task.id, deleted_at=None)
    )
    access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    _add_manager(access_service, manager_id)
    service = make_task_service(repository, access_service)

    await service.submit_for_review(task=task, actor_id=engineer_id)
    await service.return_for_revision(
        task=task,
        actor_id=manager_id,
        returned_at=datetime(2026, 10, 11, 9, 0, tzinfo=UTC),
        comment="Исправить замечания",
    )

    notification_calls = service.notification_service.calls
    assert len(notification_calls) == 1
    assert notification_calls[0]["history"].event_type == "review_rejected"
    assert notification_calls[0]["recipient_ids"] == [engineer_id]

    assert task.status is TaskStatus.IN_PROGRESS
    assert task.completed_at is None
    assert repository.history[0] is original_completion_event
    assert original_completion_event.created_at == original_completion

    await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=new_completion,
    )

    assert task.status is TaskStatus.COMPLETED
    assert task.completed_at == new_completion
    completion_events = [
        event for event in repository.history if event.event_type == "completed"
    ]
    assert [event.created_at for event in completion_events] == [
        original_completion,
        new_completion,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "status"),
    [
        ("close_task", TaskStatus.UNDER_REVIEW),
        ("return_for_revision", TaskStatus.UNDER_REVIEW),
    ],
)
async def test_review_transition_requires_access_to_task_urza(
    repository,
    access_service,
    method_name,
    status,
) -> None:
    task = _review_task(status, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    access_service.urza_repository.urzas[task.urza_id] = SimpleNamespace(
        id=task.urza_id,
        deleted_at=None,
    )
    access_service.access[(manager_id, task.urza_id)] = False
    service = make_task_service(repository, access_service)

    with pytest.raises(PermissionError, match="нет доступа к URZA"):
        await getattr(service, method_name)(task=task, actor_id=manager_id)

    assert task.status is status
    assert repository.history == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN])
@pytest.mark.parametrize("method_name", ["close_task", "return_for_revision"])
async def test_review_transitions_are_manager_only(
    repository,
    access_service,
    role,
    method_name,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW, work_type=TaskWorkType.PROGRAM)
    actor_id = uuid7()
    access_service.user_repository.users[actor_id] = SimpleNamespace(
        role=role,
        active=True,
        deleted_at=None,
    )
    service = make_task_service(repository, access_service)

    with pytest.raises(PermissionError, match="только MANAGER"):
        await getattr(service, method_name)(task=task, actor_id=actor_id)

    assert task.status is TaskStatus.UNDER_REVIEW
    assert repository.history == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "deleted_at"),
    [(False, None), (True, datetime.now())],
)
@pytest.mark.parametrize("method_name", ["close_task", "return_for_revision"])
async def test_inactive_manager_cannot_review(
    repository,
    access_service,
    active,
    deleted_at,
    method_name,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    _add_manager(
        access_service,
        manager_id,
        active=active,
        deleted_at=deleted_at,
    )
    service = make_task_service(repository, access_service)

    with pytest.raises(PermissionError, match="неактивен"):
        await getattr(service, method_name)(task=task, actor_id=manager_id)

    assert task.status is TaskStatus.UNDER_REVIEW
    assert repository.history == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "status", "target"),
    [
        ("submit_for_review", TaskStatus.IN_PROGRESS, TaskStatus.UNDER_REVIEW),
        ("close_task", TaskStatus.COMPLETED, TaskStatus.CLOSED),
        ("return_for_revision", TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS),
    ],
)
async def test_review_methods_reject_invalid_source_status(
    repository,
    access_service,
    method_name,
    status,
    target,
) -> None:
    task = _review_task(status, work_type=TaskWorkType.PROGRAM)
    service = make_task_service(repository, access_service)

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await getattr(service, method_name)(task=task, actor_id=uuid7())

    assert task.status is status
    assert repository.history == []


@pytest.mark.asyncio
async def test_close_schemes_task_requires_approved_active_schema_record(
    repository,
    access_service,
    system_user_id,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    service = make_task_service(repository, access_service)
    record = SimpleNamespace(
        task_id=task.id,
        status=DocumentStatus.APPROVED,
        deleted_at=None,
    )
    repository.schema_records.append(record)

    result = await service.close_task(task=task, actor_id=manager_id)

    assert result.status is TaskStatus.CLOSED
    assert record.status is DocumentStatus.APPROVED
    assert repository.history[-1].old_status is TaskStatus.UNDER_REVIEW
    assert repository.history[-1].new_status is TaskStatus.CLOSED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record_status",
    [DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW],
)
async def test_close_schemes_task_rejects_unapproved_schema_record(
    repository,
    access_service,
    record_status,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    repository.schema_records.append(
        SimpleNamespace(
            task_id=task.id,
            status=record_status,
            deleted_at=None,
        )
    )
    service = make_task_service(repository, access_service)

    with pytest.raises(ValueError, match="активного утверждённого результата"):
        await service.close_task(task=task, actor_id=manager_id)

    assert task.status is TaskStatus.UNDER_REVIEW
    assert repository.history == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record",
    [
        None,
        SimpleNamespace(
            task_id=uuid7(),
            status=DocumentStatus.APPROVED,
            deleted_at=datetime.now(),
        ),
    ],
)
async def test_close_schemes_task_rejects_missing_or_deleted_result(
    repository,
    access_service,
    record,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    if record is not None:
        record.task_id = task.id
        repository.schema_records.append(record)
    service = make_task_service(repository, access_service)

    with pytest.raises(ValueError, match="активного утверждённого результата"):
        await service.close_task(task=task, actor_id=manager_id)

    assert task.status is TaskStatus.UNDER_REVIEW
    assert repository.history == []


@pytest.mark.asyncio
async def test_close_non_schemes_task_keeps_existing_no_document_check(
    repository,
    access_service,
) -> None:
    task = _review_task(TaskStatus.UNDER_REVIEW, work_type=TaskWorkType.PROGRAM)
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    service = make_task_service(repository, access_service)

    result = await service.close_task(task=task, actor_id=manager_id)

    assert result.status is TaskStatus.CLOSED
    assert repository.history[-1].new_status is TaskStatus.CLOSED


@pytest.mark.asyncio
async def test_task_review_transitions_do_not_change_schema_record_status(
    repository,
    access_service,
) -> None:
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    service = make_task_service(repository, access_service)

    submit_task = _review_task(TaskStatus.COMPLETED)
    submit_task.assigned_to = manager_id
    draft_record = SimpleNamespace(
        task_id=submit_task.id,
        status=DocumentStatus.DRAFT,
        deleted_at=None,
    )
    repository.schema_records.append(draft_record)
    await service.submit_for_review(task=submit_task, actor_id=manager_id)
    assert draft_record.status is DocumentStatus.DRAFT

    return_task = _review_task(TaskStatus.UNDER_REVIEW)
    review_record = SimpleNamespace(
        task_id=return_task.id,
        status=DocumentStatus.UNDER_REVIEW,
        deleted_at=None,
    )
    repository.schema_records.append(review_record)
    await service.return_for_revision(task=return_task,
                                      actor_id=manager_id,
                                      comment="Требуется доработка",)
    assert review_record.status is DocumentStatus.UNDER_REVIEW


def _instruction_task(created_at: datetime, system_user_id) -> Task:
    return Task(
        id=uuid7(),
        urza_id=uuid7(),
        work_type=TaskWorkType.INSTRUCTION,
        created_by=system_user_id,
        assigned_to=system_user_id,
        status=TaskStatus.IN_PROGRESS,
        created_at=created_at,
        updated_by=system_user_id,
    )


def _instruction_review_task(created_at: datetime, system_user_id) -> Task:
    task = _instruction_task(created_at, system_user_id)
    task.status = TaskStatus.UNDER_REVIEW
    return task


def _instruction_review_dependencies(task: Task, system_user_id):
    repository = FakeTaskRepository()
    access_service = FakeAccessService()
    manager_id = uuid7()
    _add_manager(access_service, manager_id)
    access_service.access[(manager_id, task.urza_id)] = True
    instruction_repository = FakeURZAInstructionRepository()
    return (
        repository,
        access_service,
        manager_id,
        instruction_repository,
    )


@pytest.mark.parametrize(
    ("version_status", "version_created_at"),
    [
        (None, None),
        (DocumentStatus.DRAFT, datetime(2026, 9, 12, 10, 0)),
        (DocumentStatus.UNDER_REVIEW, datetime(2026, 9, 14, 10, 0)),
        (DocumentStatus.APPROVED, datetime(2026, 9, 12, 10, 0)),
    ],
)
@pytest.mark.asyncio
async def test_complete_urza_instruction_task_ignores_instruction_versions(
    system_user_id,
    version_status,
    version_created_at,
) -> None:
    task_created_at = datetime(2026, 9, 13, 10, 0)
    task = _instruction_task(task_created_at, system_user_id)
    instruction_repository = FakeURZAInstructionRepository()
    if version_status is not None:
        instruction = SimpleNamespace(id=uuid7())
        instruction_repository.instructions[task.urza_id] = instruction
        instruction_repository.latest_working_versions[instruction.id] = SimpleNamespace(
            status=version_status,
            created_at=version_created_at,
        )
    repository = FakeTaskRepository()
    service = make_task_service_with_active_assignee(
        repository,
        system_user_id,
        instruction_repository,
    )

    result = await service.complete_task(task=task, actor_id=system_user_id)

    assert result.status is TaskStatus.COMPLETED
    assert repository.history[-1].event_type == "completed"
    assert instruction_repository.calls == []


@pytest.mark.parametrize(
    ("version_status", "version_created_at"),
    [
        (None, None),
        (DocumentStatus.DRAFT, datetime(2026, 9, 14, 10, 0)),
        (DocumentStatus.UNDER_REVIEW, datetime(2026, 9, 12, 10, 0)),
        (DocumentStatus.APPROVED, datetime(2026, 9, 12, 10, 0)),
    ],
)
@pytest.mark.asyncio
async def test_close_urza_instruction_task_ignores_instruction_versions(
    system_user_id,
    version_status,
    version_created_at,
) -> None:
    task_created_at = datetime(2026, 9, 13, 10, 0)
    task = _instruction_review_task(task_created_at, system_user_id)
    repository, access_service, manager_id, instruction_repository = (
        _instruction_review_dependencies(task, system_user_id)
    )
    if version_status is not None:
        instruction = SimpleNamespace(id=uuid7())
        instruction_repository.instructions[task.urza_id] = instruction
        instruction_repository.latest_working_versions[instruction.id] = SimpleNamespace(
            status=version_status,
            created_at=version_created_at,
        )
    service = make_task_service(repository, access_service, instruction_repository)

    result = await service.close_task(task=task, actor_id=manager_id)

    assert result.status is TaskStatus.CLOSED
    assert repository.history[-1].event_type == "review_approved"
    assert instruction_repository.calls == []


@pytest.mark.asyncio
async def test_substation_instruction_task_still_requires_task_result(
    system_user_id,
) -> None:
    task = SimpleNamespace(
        id=uuid7(),
        urza_id=None,
        substation_id=uuid7(),
        work_type=TaskWorkType.INSTRUCTION,
        created_by=system_user_id,
        assigned_to=system_user_id,
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime(2026, 9, 13, 10, 0),
        updated_by=system_user_id,
        deleted_at=None,
    )
    repository = FakeTaskRepository()
    service = make_task_service_with_active_assignee(repository, system_user_id)

    with pytest.raises(ValueError, match="Создайте версию инструкции РЗА"):
        await service.complete_task(task=task, actor_id=system_user_id)

    assert task.status is TaskStatus.IN_PROGRESS



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "assign_task",
        "accept_task",
        "complete_task",
        "reject_task",
        "reassign_task",
        "submit_for_review",
        "close_task",
        "return_for_revision",
    ],
)
async def test_archived_task_cannot_be_modified(
    service: TaskService,
    method_name: str,
) -> None:
    task = Task(
        id=uuid7(),
        urza_id=uuid7(),
        work_type=TaskWorkType.PROGRAM,
        created_by=uuid7(),
        assigned_to=uuid7(),
        status={
            "assign_task": TaskStatus.CREATED,
            "accept_task": TaskStatus.ASSIGNED,
            "complete_task": TaskStatus.IN_PROGRESS,
            "reject_task": TaskStatus.ASSIGNED,
            "reassign_task": TaskStatus.ASSIGNED,
            "submit_for_review": TaskStatus.COMPLETED,
            "close_task": TaskStatus.UNDER_REVIEW,
            "return_for_revision": TaskStatus.UNDER_REVIEW,
        }[method_name],
    )
    task.deleted_at = datetime.now()

    original_status = task.status
    original_assignee = task.assigned_to

    method = getattr(service, method_name)
    kwargs = {
        "task": task,
        "actor_id": task.assigned_to,
    }

    if method_name in {"assign_task", "reassign_task"}:
        kwargs["assigned_to"] = uuid7()
    if method_name == "reject_task":
        kwargs["reason"] = "Тестовая причина"
    if method_name == "return_for_revision":
        kwargs["comment"] = "Тестовый комментарий"

    with pytest.raises(ValueError, match="удалённое задание"):
        await method(**kwargs)

    assert task.status is original_status
    assert task.assigned_to == original_assignee


@pytest.mark.asyncio
async def test_create_substation_instruction_task_and_reject_unsupported_type(
    service, repository, system_user_id
):
    task = await service.create_task(
        substation_id=uuid4(),
        work_type=TaskWorkType.INSTRUCTION,
        created_by=system_user_id,
    )
    assert task.urza_id is None
    assert task.substation_id is not None
    assert task.work_type is TaskWorkType.INSTRUCTION

    with pytest.raises(ValueError, match="только инструкции и схемы"):
        await service.create_task(
            substation_id=uuid4(),
            work_type=TaskWorkType.OTD,
            created_by=system_user_id,
        )


@pytest.mark.asyncio
async def test_substation_task_creation_checks_role_and_access(
    service, access_service, system_user_id
):
    engineer_id = uuid4()
    access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id, role=UserRole.ENGINEER, active=True, deleted_at=None
    )
    substation_id = uuid4()
    access_service.substation_access[(engineer_id, substation_id)] = True
    assert not await service.can_issue_task(
        actor_id=engineer_id, substation_id=substation_id
    )

    access_service.substation_access[(system_user_id, substation_id)] = False
    assert not await service.can_issue_task(
        actor_id=system_user_id, substation_id=substation_id
    )



@pytest.mark.asyncio
async def test_assign_task_rejects_actor_without_issue_permission(
    service: TaskService,
    system_user_id,
) -> None:
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )
    unauthorized_actor_id = uuid4()

    with pytest.raises(PermissionError):
        await service.assign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=unauthorized_actor_id,
        )

    assert task.status is TaskStatus.CREATED
    assert task.assigned_to is None



@pytest.mark.asyncio
async def test_reassign_task_rejects_actor_without_issue_permission(
    service: TaskService,
    system_user_id,
) -> None:
    engineer_id = uuid4()
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )

    unauthorized_actor_id = uuid4()

    with pytest.raises(PermissionError):
        await service.reassign_task(
            task=task,
            assigned_to=uuid4(),
            actor_id=unauthorized_actor_id,
        )

    assert task.status is TaskStatus.ASSIGNED
    assert task.assigned_to == engineer_id



@pytest.mark.asyncio
async def test_assign_task_rejects_unavailable_assignee(
    service: TaskService,
    access_service: FakeAccessService,
    system_user_id,
) -> None:
    urza_id = uuid7()
    enterprise_id = uuid7()
    available_engineer_id = uuid7()
    unavailable_engineer_id = uuid7()

    access_service.urza_repository.urzas[urza_id] = SimpleNamespace(
        deleted_at=None,
        connection=SimpleNamespace(
            substation=SimpleNamespace(enterprise_id=enterprise_id),
        ),
    )
    access_service.user_repository.engineers_by_enterprise[enterprise_id] = [
        SimpleNamespace(
            id=available_engineer_id,
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
    ]

    task = await service.create_task(
        urza_id=urza_id,
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    with pytest.raises(ValueError, match="доступным"):
        await service.assign_task(
            task=task,
            assigned_to=unavailable_engineer_id,
            actor_id=system_user_id,
        )

    assert task.status is TaskStatus.CREATED
    assert task.assigned_to is None



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "deleted_at"),
    [
        (False, None),
        (True, datetime(2026, 1, 1)),
    ],
)
async def test_accept_task_rejects_inactive_or_deleted_assignee(
    service: TaskService,
    access_service: FakeAccessService,
    repository: FakeTaskRepository,
    system_user_id,
    active: bool,
    deleted_at: datetime | None,
) -> None:
    engineer_id = uuid4()
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=system_user_id,
    )

    configure_available_assignee(
        service,
        urza_id=task.urza_id,
        engineer_id=engineer_id,
    )

    access_service.user_repository.users[engineer_id] = SimpleNamespace(
        id=engineer_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=system_user_id,
    )
    original_updated_by = task.updated_by

    # После назначения учётная запись становится неактивной
    # либо помечается удалённой.
    access_service.user_repository.users[engineer_id].active = active
    access_service.user_repository.users[engineer_id].deleted_at = deleted_at

    history_count = len(repository.history)

    with pytest.raises(PermissionError):
        await service.accept_task(
            task=task,
            actor_id=engineer_id,
        )

    assert task.status is TaskStatus.ASSIGNED
    assert task.assigned_to == engineer_id
    assert task.updated_by == original_updated_by
    assert len(repository.history) == history_count

    # Принятие задания само по себе не создаёт уведомление.
    assert len(service.notification_service.calls) == 1
    assert service.notification_service.calls[0]["history"].event_type == "assigned"



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "status", "active", "deleted_at"),
    [
        ("reject_task", TaskStatus.ASSIGNED, False, None),
        ("reject_task", TaskStatus.ASSIGNED, True, datetime(2026, 1, 1)),
        ("complete_task", TaskStatus.IN_PROGRESS, False, None),
        ("complete_task", TaskStatus.IN_PROGRESS, True, datetime(2026, 1, 1)),
        ("submit_for_review", TaskStatus.COMPLETED, False, None),
        ("submit_for_review", TaskStatus.COMPLETED, True, datetime(2026, 1, 1)),
    ],
)
async def test_executor_actions_reject_inactive_or_deleted_assignee(
    service: TaskService,
    repository: FakeTaskRepository,
    access_service: FakeAccessService,
    system_user_id,
    method_name: str,
    status: TaskStatus,
    active: bool,
    deleted_at: datetime | None,
) -> None:
    actor_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=system_user_id,
    )
    task.assigned_to = actor_id
    task.status = status

    access_service.user_repository.users[actor_id] = SimpleNamespace(
        id=actor_id,
        role=UserRole.ENGINEER,
        active=active,
        deleted_at=deleted_at,
    )

    history_count = len(repository.history)
    original_updated_by = task.updated_by

    kwargs = {
        "task": task,
        "actor_id": actor_id,
    }
    if method_name == "reject_task":
        kwargs["reason"] = "Тестовая причина"

    with pytest.raises(PermissionError):
        await getattr(service, method_name)(**kwargs)

    assert task.status is status
    assert task.assigned_to == actor_id
    assert task.updated_by == original_updated_by
    assert len(repository.history) == history_count
