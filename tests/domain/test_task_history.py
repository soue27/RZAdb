from datetime import datetime, timezone

from app.domain.enums import TaskStatus
from app.domain.task_history import TaskHistory


def test_task_history_model() -> None:
    created_at = datetime.now(timezone.utc)

    history = TaskHistory(
        event_type="created",
        old_status=None,
        new_status=TaskStatus.CREATED,
        created_at=created_at,
    )

    assert history.event_type == "created"
    assert history.old_status is None
    assert history.new_status == TaskStatus.CREATED
    assert history.comment is None
    assert history.created_at == created_at
    assert history.task_id is None
    assert history.actor_id is None