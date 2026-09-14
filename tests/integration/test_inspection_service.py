from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.substations.repository import SubstationRepository
from app.application.users.repository import UserRepository
from app.domain.enums import (
    AccessCategory,
    EnterpriseType,
    HighestVoltage,
    TaskStatus,
    UserRole,
)
from app.domain.enterprise import Enterprise
from app.domain.substation import Substation
from app.domain.user import User
from sqlalchemy import select

from app.domain.inspection_history import InspectionHistory
from app.domain.inspection import Inspection


@pytest.mark.asyncio
async def test_create_inspection_task_with_real_postgresql(
    db_session,
) -> None:
    """Проверяем создание задачи осмотра через сервис и PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое производственное отделение",
        short_name="Тестовое ПО",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Сервисная",
    )

    db_session.add_all(
        [
            department,
            manager,
            substation,
        ]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    now = datetime.now(timezone.utc)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=now,
    )

    assert task.id is not None
    assert task.substation_id == substation.id
    assert task.created_by == manager.id
    assert task.status == TaskStatus.CREATED

    assert task.deadline_at == now + timedelta(days=7)
    assert task.assigned_to is None
    assert task.assigned_at is None
    assert task.acceptance_deadline_at is None
    assert task.completed_at is None
    assert task.closed_at is None

    # Проверяем, что сервис действительно создал запись в PostgreSQL.
    saved_task = await task_repository.get_by_id(task.id)

    assert saved_task is not None
    assert saved_task.id == task.id
    assert saved_task.substation_id == substation.id
    assert saved_task.created_by == manager.id
    assert saved_task.status == TaskStatus.CREATED

@pytest.mark.asyncio
async def test_assign_inspection_task_with_real_postgresql(
    db_session,
) -> None:
    """Проверяем назначение задачи исполнителю через PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО для назначения",
        short_name="ПО Назначение",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    engineer = User(
        id=uuid4(),
        full_name="Петров Петр Петрович",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Назначение",
    )

    db_session.add_all(
        [
            department,
            manager,
            engineer,
            substation,
        ]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    created_at = datetime.now(timezone.utc)
    assigned_at = created_at + timedelta(hours=2)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=created_at,
    )

    result = await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=assigned_at,
    )

    assert result.status == TaskStatus.ASSIGNED
    assert result.assigned_to == engineer.id
    assert result.assigned_at == assigned_at
    assert result.acceptance_deadline_at == assigned_at + timedelta(days=1)

    # Общий deadline задачи отсчитывается от создания
    # и не меняется при назначении исполнителя.
    assert result.deadline_at == created_at + timedelta(days=7)

    history = await db_session.execute(
        select(InspectionHistory).where(
            InspectionHistory.inspection_task_id == task.id
        )
    )
    history_records = history.scalars().all()

    assert len(history_records) == 1

    history_record = history_records[0]

    assert history_record.event_type == "assigned"
    assert history_record.old_status == TaskStatus.CREATED
    assert history_record.new_status == TaskStatus.ASSIGNED
    assert history_record.actor_id == manager.id

@pytest.mark.asyncio
async def test_accept_inspection_task_with_real_postgresql(
    db_session,
) -> None:
    """Проверяем принятие задачи исполнителем через PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО для принятия",
        short_name="ПО Принятие",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    engineer = User(
        id=uuid4(),
        full_name="Петров Петр Петрович",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Принятие",
    )

    db_session.add_all(
        [
            department,
            manager,
            engineer,
            substation,
        ]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    created_at = datetime.now(timezone.utc)
    assigned_at = created_at + timedelta(hours=2)
    accepted_at = assigned_at + timedelta(hours=1)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=created_at,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=assigned_at,
    )

    result = await service.accept(
        task.id,
        actor_id=engineer.id,
        now=accepted_at,
    )

    assert result.status == TaskStatus.IN_PROGRESS
    assert result.assigned_to == engineer.id

    # Принятие задачи не должно менять установленные сроки.
    assert result.assigned_at == assigned_at
    assert result.acceptance_deadline_at == assigned_at + timedelta(days=1)
    assert result.deadline_at == created_at + timedelta(days=7)

    assert result.completed_at is None
    assert result.closed_at is None

    history_result = await db_session.execute(
        select(InspectionHistory)
        .where(InspectionHistory.inspection_task_id == task.id)
        .order_by(InspectionHistory.created_at)
    )
    history_records = history_result.scalars().all()

    assert len(history_records) == 2

    accepted_history = history_records[-1]

    assert accepted_history.event_type == "accepted"
    assert accepted_history.old_status == TaskStatus.ASSIGNED
    assert accepted_history.new_status == TaskStatus.IN_PROGRESS
    assert accepted_history.actor_id == engineer.id

@pytest.mark.asyncio
async def test_complete_inspection_task_with_real_postgresql(
    db_session,
) -> None:
    """Проверяем завершение осмотра и создание результата в PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО для завершения",
        short_name="ПО Завершение",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    engineer = User(
        id=uuid4(),
        full_name="Петров Петр Петрович",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Завершение",
    )

    db_session.add_all(
        [
            department,
            manager,
            engineer,
            substation,
        ]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    created_at = datetime.now(timezone.utc)
    assigned_at = created_at + timedelta(hours=2)
    accepted_at = assigned_at + timedelta(hours=1)
    completed_at = accepted_at + timedelta(hours=3)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=created_at,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=assigned_at,
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
        now=accepted_at,
    )

    result = await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=completed_at.date(),
        remarks="Замечаний не выявлено",
        now=completed_at,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.assigned_to == engineer.id
    assert result.completed_at == completed_at

    # Срок выполнения задачи устанавливается при создании
    # и не меняется после завершения осмотра.
    assert result.deadline_at == created_at + timedelta(days=7)

    inspection_result = await db_session.execute(
        select(Inspection).where(
            Inspection.inspection_task_id == task.id
        )
    )
    inspections = inspection_result.scalars().all()

    assert len(inspections) == 1

    inspection = inspections[0]

    assert inspection.substation_id == substation.id
    assert inspection.inspection_task_id == task.id
    assert inspection.inspection_date == completed_at.date()
    assert inspection.remarks == "Замечаний не выявлено"

    # Файлы для осмотра необязательны.
    assert inspection.scan_file_id is None
    assert inspection.editable_file_id is None

    history_result = await db_session.execute(
        select(InspectionHistory)
        .where(
            InspectionHistory.inspection_task_id == task.id
        )
        .order_by(InspectionHistory.created_at)
    )
    history_records = history_result.scalars().all()

    assert len(history_records) == 3

    completed_history = history_records[-1]

    assert completed_history.event_type == "completed"
    assert completed_history.old_status == TaskStatus.IN_PROGRESS
    assert completed_history.new_status == TaskStatus.COMPLETED
    assert completed_history.actor_id == engineer.id

@pytest.mark.asyncio
async def test_cannot_complete_inspection_without_remarks(
    db_session,
) -> None:
    """Проверяем обязательность замечаний при завершении осмотра."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО — обязательные замечания",
        short_name="ПО Remarks",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    engineer = User(
        id=uuid4(),
        full_name="Петров Петр Петрович",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Remarks",
    )

    db_session.add_all(
        [department, manager, engineer, substation]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    now = datetime.now(timezone.utc)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=now,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=now + timedelta(hours=1),
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
        now=now + timedelta(hours=2),
    )

    with pytest.raises(ValueError, match="замечания"):
        await service.complete(
            task.id,
            actor_id=engineer.id,
            inspection_date=now.date(),
            remarks="   ",
            now=now + timedelta(hours=3),
        )

    saved_task = await task_repository.get_by_id(task.id)

    assert saved_task is not None
    assert saved_task.status == TaskStatus.IN_PROGRESS
    assert saved_task.completed_at is None

@pytest.mark.asyncio
async def test_send_inspection_to_review_with_real_postgresql(
    db_session,
) -> None:
    """Проверяем передачу завершённого осмотра на проверку."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО — проверка",
        short_name="ПО Review",
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    engineer = User(
        id=uuid4(),
        full_name="Петров Петр Петрович",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Review",
    )

    db_session.add_all(
        [
            department,
            manager,
            engineer,
            substation,
        ]
    )
    await db_session.flush()

    task_repository = InspectionTaskRepository(db_session)
    user_repository = UserRepository(db_session)
    substation_repository = SubstationRepository(db_session)

    service = InspectionTaskService(
        task_repository,
        user_repository,
        substation_repository,
    )

    created_at = datetime.now(timezone.utc)
    assigned_at = created_at + timedelta(hours=1)
    accepted_at = assigned_at + timedelta(hours=1)
    completed_at = accepted_at + timedelta(hours=2)
    review_at = completed_at + timedelta(hours=1)

    task = await service.create(
        substation_id=substation.id,
        created_by=manager.id,
        now=created_at,
    )

    await service.assign(
        task.id,
        actor_id=manager.id,
        assignee_id=engineer.id,
        now=assigned_at,
    )

    await service.accept(
        task.id,
        actor_id=engineer.id,
        now=accepted_at,
    )

    await service.complete(
        task.id,
        actor_id=engineer.id,
        inspection_date=completed_at.date(),
        remarks="Замечаний не выявлено",
        now=completed_at,
    )

    result = await service.send_to_review(
        task.id,
        actor_id=engineer.id,
        now=review_at,
    )

    assert result.status == TaskStatus.UNDER_REVIEW
    assert result.assigned_to == engineer.id
    assert result.completed_at == completed_at
    assert result.closed_at is None

    # Передача на проверку не изменяет сроки задачи.
    assert result.assigned_at == assigned_at
    assert result.acceptance_deadline_at == assigned_at + timedelta(days=1)
    assert result.deadline_at == created_at + timedelta(days=7)

    history_result = await db_session.execute(
        select(InspectionHistory)
        .where(
            InspectionHistory.inspection_task_id == task.id
        )
        .order_by(InspectionHistory.created_at)
    )
    history_records = history_result.scalars().all()

    assert len(history_records) == 4

    review_history = history_records[-1]

    assert review_history.event_type == "sent_to_review"
    assert review_history.old_status == TaskStatus.COMPLETED
    assert review_history.new_status == TaskStatus.UNDER_REVIEW
    assert review_history.actor_id == engineer.id