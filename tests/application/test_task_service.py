from datetime import datetime
from uuid import uuid4

import pytest

from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.otd import OTDVersion
from app.domain.settings_record import SettingsRecord
from app.domain.task import Task
from app.domain.schema import SchemaRecord
from app.domain.program import Program, ProgramType
from app.domain.maintenance import TORecord


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

    async def get_otd_version_by_task_id(self, task_id):
        """Возвращает версию ОТД, связанную с указанной задачей."""
        return next(
            (
                version
                for version in self.otd_versions
                if version.task_id == task_id
            ),
            None,
        )

    async def get_settings_record_by_task_id(self, task_id):
        """Возвращает запись уставок, связанную с указанной задачей."""
        return next(
            (
                record
                for record in self.settings_records
                if record.task_id == task_id
            ),
            None,
        )

    async def get_schema_record_by_task_id(self, task_id):
        """Возвращает запись схем, связанную с указанной задачей."""
        return next(
            (
                record
                for record in self.schema_records
                if record.task_id == task_id
            ),
            None,
        )

    async def get_program_by_task_id(self, task_id):
        """Возвращает программу, связанную с указанной задачей."""
        return next(
            (
                program
                for program in self.programs
                if program.task_id == task_id
            ),
            None,
        )

    async def get_to_record_by_task_id(self, task_id):
        """Возвращает запись ТО, связанную с указанной задачей."""
        return next(
            (
                record
                for record in self.to_records
                if record.task_id == task_id
            ),
            None,
        )


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

@pytest.mark.asyncio
async def test_complete_task(
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    created_at = datetime(2026, 9, 13, 10, 0)
    assigned_at = datetime(2026, 9, 13, 12, 0)
    completed_at = datetime(2026, 9, 15, 14, 30)

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
    )

    # Результат ОТД необходим для успешного завершения задачи.
    otd_version = OTDVersion(
        otd_id=uuid4(),
        version_number=1,
        effective_date=completed_at.date(),
        urza_service_life=10,
        urza_purpose="rza",
        task_id=task.id,
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


@pytest.mark.asyncio
async def test_complete_task_only_by_assigned_engineer(
    service: TaskService,
) -> None:
    """Проверяет, что завершить задачу может только её исполнитель."""
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
    service: TaskService,
) -> None:
    """Проверяет, что завершение разрешено только для задачи в работе."""
    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.OTD,
        created_by=uuid4(),
    )

    engineer_id = uuid4()

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Недопустимый переход"):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_otd_task_requires_otd_version(
    service: TaskService,
) -> None:
    """Проверяет, что ОТД-задачу нельзя завершить без результата ОТД."""
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
    service: TaskService,
    repository: FakeTaskRepository,
) -> None:
    """Проверяет завершение ОТД-задачи при наличии результата ОТД."""
    engineer_id = uuid4()
    completed_at = datetime(2026, 9, 15, 14, 30)

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
    service: TaskService,
) -> None:
    """Проверяет, что задачу по уставкам нельзя завершить без результата."""
    engineer_id = uuid4()

    task = await service.create_task(
        urza_id=uuid4(),
        work_type=TaskWorkType.SETTINGS,
        created_by=uuid4(),
    )

    await service.assign_task(
        task=task,
        assigned_to=engineer_id,
        actor_id=uuid4(),
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
async def test_complete_settings_task_with_result() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SETTINGS,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.settings_records.append(settings_record)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_schemes_task_requires_schema_record() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по схемам необходимо сохранить результат схем",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_schemes_task_with_scan_and_signed_form() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.schema_records.append(schema_record)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at


@pytest.mark.asyncio
async def test_complete_schemes_task_requires_signed_form() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.schema_records.append(schema_record)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="подписан",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_schemes_task_requires_scan_or_editable_file() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.schema_records.append(schema_record)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="скан или редактируемый файл",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_schemes_task_with_editable_and_signed_form() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.SCHEMES,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.schema_records.append(schema_record)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_program_task_requires_program() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по программе необходимо сохранить программу",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_program_task_with_scan() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.programs.append(program)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_program_task_with_scan() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.PROGRAM,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.programs.append(program)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_to_record() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
    )

    repository = FakeTaskRepository()
    repository.tasks.append(task)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="Для завершения задачи по ТО необходимо сохранить результат ТО",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )


@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_protocol() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.to_records.append(to_record)

    service = TaskService(repository)

    with pytest.raises(
        ValueError,
        match="протокол",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )

@pytest.mark.asyncio
async def test_complete_maintenance_task_without_protocol_for_tk() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.TK,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.to_records.append(to_record)

    service = TaskService(repository)

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
    maintenance_type: MaintenanceType,
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
    )
    repository.to_records.append(to_record)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_maintenance_task_with_protocol() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.to_records.append(to_record)

    service = TaskService(repository)

    completed_at = datetime.now().astimezone()

    result = await service.complete_task(
        task=task,
        actor_id=engineer_id,
        completed_at=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.completed_at == completed_at

@pytest.mark.asyncio
async def test_complete_maintenance_task_requires_matching_maintenance_type() -> None:
    engineer_id = uuid4()

    task = Task(
        id=uuid4(),
        urza_id=uuid4(),
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K,
        created_by=engineer_id,
        assigned_to=engineer_id,
        status=TaskStatus.IN_PROGRESS,
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
    )
    repository.to_records.append(to_record)

    service = TaskService(repository)

    with pytest.raises(
            ValueError,
            match="Вид ТО в результате не соответствует виду ТО в задаче",
    ):
        await service.complete_task(
            task=task,
            actor_id=engineer_id,
        )