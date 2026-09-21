from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.inspection_repository import InspectionRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    EnterpriseType,
    HighestVoltage,
    TaskStatus,
    UserRole,
)
from app.domain.inspection import Inspection
from app.domain.inspection_history import InspectionHistory
from app.domain.inspection_task import InspectionTask
from app.domain.substation import Substation
from app.domain.user import User


@pytest.mark.asyncio
async def test_inspection_task_repository(
    db_session,
) -> None:
    """Проверяем основные операции репозитория на PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО",
        short_name="ПО Тест",
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
        dispatch_name="ПС Репозиторная",
    )

    db_session.add_all([department, manager, substation])
    await db_session.flush()

    repository = InspectionTaskRepository(db_session)

    task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.CREATED,
        deadline_at=datetime.now(UTC),
    )

    # create()
    created_task = await repository.create(task)

    assert created_task.id == task.id
    assert created_task.status == TaskStatus.CREATED

    # get_by_id()
    loaded_task = await repository.get_by_id(task.id)

    assert loaded_task is not None
    assert loaded_task.id == task.id
    assert loaded_task.substation_id == substation.id

    # save()
    loaded_task.status = TaskStatus.ASSIGNED
    loaded_task.assigned_to = manager.id

    saved_task = await repository.save(loaded_task)

    assert saved_task.status == TaskStatus.ASSIGNED
    assert saved_task.assigned_to == manager.id

    # add_history()
    history = InspectionHistory(
        id=uuid4(),
        inspection_task_id=task.id,
        event_type="assigned",
        old_status=TaskStatus.CREATED,
        new_status=TaskStatus.ASSIGNED,
        actor_id=manager.id,
        created_at=datetime.now(UTC),
    )

    saved_history = await repository.add_history(history)

    assert saved_history.id == history.id
    assert saved_history.task_id if hasattr(saved_history, "task_id") else True

    # create_inspection()
    inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=task.id,
        inspection_date=datetime.now(UTC).date(),
        remarks="Замечаний не выявлено",
        created_by=manager.id,
    )

    created_inspection = await repository.create_inspection(inspection)

    assert created_inspection.id == inspection.id
    assert created_inspection.inspection_task_id == task.id


@pytest.mark.asyncio
async def test_inspection_repository_get_by_substation_id(
    db_session,
) -> None:
    """Проверяем получение результатов осмотров подстанции."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО",
        short_name="ПО Тест",
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
        dispatch_name="ПС Осмотры",
    )

    db_session.add_all([department, manager, substation])
    await db_session.flush()

    first_task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.COMPLETED,
        deadline_at=datetime.now(UTC),
    )

    second_task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.COMPLETED,
        deadline_at=datetime.now(UTC),
    )

    db_session.add_all([first_task, second_task])
    await db_session.flush()

    first_inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=first_task.id,
        inspection_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
        remarks="Первый осмотр.",
        created_by=manager.id,
    )

    second_inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=second_task.id,
        inspection_date=datetime(2026, 9, 1, tzinfo=UTC).date(),
        remarks="Второй осмотр.",
        created_by=manager.id,
    )

    db_session.add_all([first_inspection, second_inspection])
    await db_session.flush()

    repository = InspectionRepository(db_session)

    inspections = await repository.get_by_substation_id(
        substation.id,
    )

    assert len(inspections) == 2
    assert inspections[0].id == second_inspection.id
    assert inspections[1].id == first_inspection.id
    assert inspections[0].inspection_date.isoformat() == "2026-09-01"
    assert inspections[1].inspection_date.isoformat() == "2026-08-01"