from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.task import Task


def test_task_model() -> None:
    task = Task(
        work_type=TaskWorkType.MAINTENANCE,
        maintenance_type=MaintenanceType.K1,
        description="Провести профилактический контроль",
        status=TaskStatus.CREATED,
    )

    assert task.work_type == TaskWorkType.MAINTENANCE
    assert task.maintenance_type == MaintenanceType.K1
    assert task.description == "Провести профилактический контроль"
    assert task.status == TaskStatus.CREATED

    assert task.urza_id is None
    assert task.created_by is None
    assert task.assigned_to is None
    assert task.assigned_at is None
    assert task.acceptance_deadline_at is None
    assert task.deadline_at is None
    assert task.completed_at is None
    assert task.closed_at is None