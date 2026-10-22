from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.programs.repository import ProgramRepository
from app.application.programs.service import ProgramService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    DocumentStatus,
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    ProgramType,
    RoomCategory,
    TaskStatus,
    TaskWorkType,
    URZACategory,
    URZAStatus,
    UserRole,
)
from app.domain.file import File
from app.domain.program import Program
from app.domain.substation import Substation
from app.domain.task import Task
from app.domain.task_history import TaskHistory
from app.domain.urza import URZA
from app.domain.user import User


@pytest.mark.asyncio
async def test_database_transaction_is_rolled_back(
    db_session,
    system_user_id,
) -> None:
    enterprise = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Rollback Test Department",
        short_name="Rollback Test",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    db_session.add(enterprise)
    await db_session.flush()

    saved_id = enterprise.id

    result = await db_session.get(Enterprise, saved_id)
    assert result is not None
    assert result.full_name == "Rollback Test Department"


@pytest.mark.asyncio
async def test_program_submission_rolls_back_task_and_history(
    db_session,
    system_user_id,
    monkeypatch,
) -> None:
    """При ошибке сохранения программы откатываются задача и её история."""

    department = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="Atomicity Test Department",
        short_name="ATOMICITY",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    engineer = User(
        full_name="Тестовый инженер",
        role=UserRole.ENGINEER,
        email=f"{uuid4()}@example.com",
        password_hash="test-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    substation = Substation(
        enterprise=department,
        highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        dispatch_name="Atomicity PS",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    connection = Connection(
        substation=substation,
        dispatch_name="Atomicity Connection",
        rdu_subordination=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    urza = URZA(
        connection=connection,
        dispatch_name="Atomicity URZA",
        rdu_subordination=False,
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    scan_file = File(
        id=uuid4(),
        s3_key=f"tests/atomicity/{uuid4()}.pdf",
        original_name="program.pdf",
        display_name="Program",
        extension=".pdf",
        size=1,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    db_session.add_all(
        [
            department,
            engineer,
            substation,
            connection,
            urza,
            scan_file,
        ]
    )
    await db_session.flush()

    task = Task(
        id=uuid4(),
        urza_id=urza.id,
        work_type=TaskWorkType.PROGRAM,
        status=TaskStatus.IN_PROGRESS,
        deadline_at=datetime.now(UTC) + timedelta(days=7),
        created_by=engineer.id,
        assigned_to=engineer.id,
        updated_by=engineer.id,
    )

    program = Program(
        id=uuid4(),
        urza_id=urza.id,
        program_type=ProgramType.WORK,
        program_number="ATOMICITY-001",
        status=DocumentStatus.DRAFT,
        scan_file_id=scan_file.id,
        task_id=task.id,
        created_by=engineer.id,
        updated_by=engineer.id,
    )

    db_session.add_all(
        [
            task,
            program,
        ]
    )
    await db_session.flush()

    task_id = task.id
    program_id = program.id
    urza_id = urza.id
    engineer_id = engineer.id

    # Все исходные данные уже записаны в тестовую транзакцию.
    # Операцию проверяем внутри отдельного SAVEPOINT.
    savepoint = await db_session.begin_nested()

    user_repository = UserRepository(db_session)
    task_repository = TaskRepository(db_session)
    program_repository = ProgramRepository(db_session)
    urza_repository = URZARepository(db_session)

    class AllowURZAAccess:
        def __init__(self, user_repository):
            self.user_repository = user_repository

        async def can_access_urza(self, user_id, requested_urza_id):
            return (
                user_id == engineer_id
                and requested_urza_id == urza_id
            )

    access_service = AllowURZAAccess(user_repository)

    task_service = TaskService(
        task_repository=task_repository,
        access_service=access_service,
        urza_instruction_repository=None,
    )

    program_service = ProgramService(
        repository=program_repository,
        access_service=access_service,
        user_repository=user_repository,
        urza_repository=urza_repository,
        task_repository=task_repository,
        task_service=task_service,
    )

    async def fail_program_save(_program):
        raise RuntimeError("Искусственная ошибка сохранения программы")

    monkeypatch.setattr(program_repository, "save", fail_program_save)

    with pytest.raises(RuntimeError, match="Искусственная ошибка"):
        await program_service.submit_for_review(
            user_id=engineer_id,
            program_id=program_id,
            urza_id=urza_id,
        )

    await savepoint.rollback()
    db_session.expire_all()

    saved_task = await db_session.get(Task, task_id)
    saved_program = await db_session.get(Program, program_id)

    assert saved_task is not None
    assert saved_task.status == TaskStatus.IN_PROGRESS

    assert saved_program is not None
    assert saved_program.status == DocumentStatus.DRAFT

    history = await db_session.scalars(
        select(TaskHistory).where(TaskHistory.task_id == task_id)
    )
    assert list(history) == []
