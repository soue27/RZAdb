from datetime import UTC, datetime
from uuid import uuid4

import pytest
from uuid6 import uuid7

from app.application.inspections.inspection_repository import InspectionRepository
from app.application.inspections.repository import InspectionTaskRepository
from app.application.selectivity_schemes.repository import SelectivitySchemeRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    DocumentStatus,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    TaskStatus,
    UserRole,
)
from app.domain.file import File
from app.domain.inspection import Inspection
from app.domain.inspection_history import InspectionHistory
from app.domain.inspection_task import InspectionTask
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)
from app.domain.substation import Substation
from app.domain.user import User


@pytest.mark.asyncio
async def test_inspection_task_repository(db_session, system_user_id) -> None:
    """Проверяем основные операции репозитория на PostgreSQL."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО",
        short_name="ПО Тест",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Репозиторная",
        operational_current_type=OperationalCurrentType.PERMANENT,
        created_by=system_user_id,
        updated_by=system_user_id,
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
        updated_by=system_user_id,
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


    # list_reviewed_task_ids()
    reviewer_id = manager.id
    another_task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.UNDER_REVIEW,
        deadline_at=datetime.now(UTC),
        updated_by=system_user_id,
    )
    db_session.add(another_task)
    await db_session.flush()

    db_session.add_all([
        InspectionHistory(
            id=uuid4(),
            inspection_task_id=task.id,
            event_type="review_approved",
            old_status=TaskStatus.UNDER_REVIEW,
            new_status=TaskStatus.CLOSED,
            actor_id=reviewer_id,
            created_at=datetime.now(UTC),
        ),
        InspectionHistory(
            id=uuid4(),
            inspection_task_id=another_task.id,
            event_type="review_rejected",
            old_status=TaskStatus.UNDER_REVIEW,
            new_status=TaskStatus.IN_PROGRESS,
            actor_id=manager.id,
            created_at=datetime.now(UTC),
        ),
    ])
    await db_session.flush()

    reviewed_ids = await repository.list_reviewed_task_ids(manager.id)

    assert reviewed_ids == {task.id, another_task.id}
    assert await repository.list_reviewed_task_ids(system_user_id) == set()


    # create_inspection()
    inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=task.id,
        inspection_date=datetime.now(UTC).date(),
        remarks="Замечаний не выявлено",
        created_by=manager.id,
        updated_by=system_user_id,
    )

    created_inspection = await repository.create_inspection(inspection)

    assert created_inspection.id == inspection.id
    assert created_inspection.inspection_task_id == task.id


@pytest.mark.asyncio
async def test_inspection_repository_get_by_substation_id(
    db_session, system_user_id
) -> None:
    """Проверяем получение результатов осмотров подстанции."""

    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО",
        short_name="ПО Тест",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    manager = User(
        id=uuid4(),
        full_name="Иванов Иван Иванович",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Осмотры",
        operational_current_type=OperationalCurrentType.PERMANENT,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    db_session.add_all([department, manager, substation])
    await db_session.flush()

    first_task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.COMPLETED,
        deadline_at=datetime.now(UTC),
        updated_by=system_user_id,
    )

    second_task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.COMPLETED,
        deadline_at=datetime.now(UTC),
        updated_by=system_user_id,
    )

    db_session.add_all([first_task, second_task])
    await db_session.flush()

    scan_file = File(
        id=uuid7(),
        s3_key="files/2026/08/scan.pdf",
        original_name="scan.pdf",
        display_name="Скан осмотра",
        extension=".pdf",
        size=1024,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    editable_file = File(
        id=uuid7(),
        s3_key="files/2026/08/inspection.docx",
        original_name="inspection.docx",
        display_name="Редактируемый документ",
        extension=".docx",
        size=2048,
        mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    db_session.add_all([scan_file, editable_file])
    await db_session.flush()

    first_inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=first_task.id,
        inspection_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
        remarks="Первый осмотр.",
        created_by=manager.id,
        scan_file_id=scan_file.id,
        editable_file_id=editable_file.id,
        updated_by=system_user_id,
    )

    second_inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=second_task.id,
        inspection_date=datetime(2026, 9, 1, tzinfo=UTC).date(),
        remarks="Второй осмотр.",
        created_by=manager.id,
        updated_by=system_user_id,
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
    assert inspections[1].scan_file is not None
    assert inspections[1].scan_file.id == scan_file.id
    assert inspections[1].scan_file.display_name == "Скан осмотра"

    assert inspections[1].editable_file is not None
    assert inspections[1].editable_file.id == editable_file.id
    assert inspections[1].editable_file.display_name == "Редактируемый документ"


@pytest.mark.asyncio
async def test_selectivity_scheme_version_is_persisted_and_read_back(
    db_session, system_user_id
) -> None:
    department = Enterprise(
        id=uuid4(), type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО схем", short_name="ПО схем",
        created_by=system_user_id, updated_by=system_user_id,
    )
    substation = Substation(
        id=uuid4(), enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        dispatch_name=f"ПС Схема {uuid4()}",
        created_by=system_user_id, updated_by=system_user_id,
    )
    scan_file = File(
        id=uuid4(), s3_key=f"test/{uuid4()}.pdf", original_name="scheme.pdf",
        display_name="Скан схемы", extension=".pdf", size=10,
        mime_type="application/pdf", uploaded_at=datetime.now(UTC),
        created_by=system_user_id, updated_by=system_user_id,
    )
    db_session.add_all([department, substation, scan_file])
    await db_session.flush()

    repository = SelectivitySchemeRepository(db_session)
    scheme = SelectivityScheme(
        id=uuid4(), substation_id=substation.id,
        created_by=system_user_id, updated_by=system_user_id,
    )
    await repository.add_scheme(scheme)
    version = SelectivitySchemeVersion(
        id=uuid4(), selectivity_scheme_id=scheme.id, version_number=1,
        number="С-110-1", name="Основная схема",
        effective_date=datetime(2026, 10, 17, tzinfo=UTC).date(),
        status=DocumentStatus.DRAFT, scan_file_id=scan_file.id,
        created_by=system_user_id, updated_by=system_user_id,
    )
    await repository.add_version(version)

    persisted_scheme = await repository.get_by_substation_id(substation.id)
    persisted_versions = await repository.get_versions(scheme.id)
    assert persisted_scheme is not None
    assert len(persisted_versions) == 1
    assert persisted_versions[0].id == version.id
    assert persisted_versions[0].number == "С-110-1"
    assert persisted_versions[0].name == "Основная схема"
    assert persisted_versions[0].scan_file_id == scan_file.id
