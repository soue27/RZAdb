from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    EnterpriseType,
    HighestVoltage,
    TaskStatus,
    UserRole, OperationalCurrentType,
)
from app.domain.inspection import Inspection
from app.domain.inspection_task import InspectionTask
from app.domain.substation import Substation
from app.domain.user import User


@pytest.mark.asyncio
async def test_inspection_models_can_be_saved_to_postgresql(db_session) -> None:
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
        dispatch_name="ПС Тестовая",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    task = InspectionTask(
        id=uuid4(),
        substation_id=substation.id,
        created_by=manager.id,
        status=TaskStatus.CREATED,
        deadline_at=datetime.now(UTC),
    )

    db_session.add_all(
        [
            department,
            manager,
            substation,
            task,
        ]
    )

    await db_session.flush()

    inspection = Inspection(
        id=uuid4(),
        substation_id=substation.id,
        inspection_task_id=task.id,
        inspection_date=date.today(),
        remarks="Замечаний не выявлено",
        created_by=manager.id,
    )

    db_session.add(inspection)

    await db_session.flush()

    saved_inspection = await db_session.get(
        Inspection,
        inspection.id,
    )
    saved_task = await db_session.get(
        InspectionTask,
        task.id,
    )

    assert saved_inspection is not None
    assert saved_task is not None

    assert saved_inspection.substation_id == substation.id
    assert saved_inspection.inspection_task_id == saved_task.id
    assert saved_inspection.inspection_date == date.today()
    assert saved_inspection.remarks == "Замечаний не выявлено"

    assert saved_task.substation_id == substation.id
    assert saved_task.status == TaskStatus.CREATED