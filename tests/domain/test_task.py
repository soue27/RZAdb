from uuid import uuid4

from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.task import Task


def test_task_model(system_user_id) -> None:
    task = Task(
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K1,
        description="Провести профилактический контроль",
        status=TaskStatus.CREATED,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    assert task.work_type == TaskWorkType.MAINTENANCE
    assert task.maintenance_type == MaintenanceType.K1
    assert task.description == "Провести профилактический контроль"
    assert task.status == TaskStatus.CREATED

    assert task.urza_id is None
    assert task.created_by == system_user_id
    assert task.assigned_to is None
    assert task.assigned_at is None
    assert task.acceptance_deadline_at is None
    assert task.deadline_at is None
    assert task.completed_at is None
    assert task.closed_at is None


def test_task_model_supports_substation_parent_and_constraints(system_user_id) -> None:
    task = Task(
        substation_id=uuid4(),
        work_type=TaskWorkType.INSTRUCTION,
        status=TaskStatus.CREATED,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    assert task.urza_id is None
    assert task.substation_id is not None
    constraints = {constraint.name for constraint in Task.__table__.constraints}
    assert "ck_tasks_exactly_one_parent" in constraints
    assert "ck_tasks_substation_work_type" in constraints
    assert "ix_tasks_substation_id" in {index.name for index in Task.__table__.indexes}
