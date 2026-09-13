import pytest

from app.application.inspections.workflow import (
    can_transition,
    validate_reason,
    validate_transition,
)
from app.domain.enums import TaskStatus


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (TaskStatus.CREATED, TaskStatus.ASSIGNED),
        (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS),
        (TaskStatus.ASSIGNED, TaskStatus.REJECTED),
        (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED),
        (TaskStatus.COMPLETED, TaskStatus.UNDER_REVIEW),
        (TaskStatus.UNDER_REVIEW, TaskStatus.CLOSED),
        (TaskStatus.UNDER_REVIEW, TaskStatus.IN_PROGRESS),
    ],
)
def test_allowed_transition(
    current: TaskStatus,
    new: TaskStatus,
) -> None:
    assert can_transition(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (TaskStatus.CREATED, TaskStatus.IN_PROGRESS),
        (TaskStatus.CREATED, TaskStatus.COMPLETED),
        (TaskStatus.ASSIGNED, TaskStatus.CLOSED),
        (TaskStatus.IN_PROGRESS, TaskStatus.CLOSED),
        (TaskStatus.COMPLETED, TaskStatus.CLOSED),
        (TaskStatus.CLOSED, TaskStatus.IN_PROGRESS),
        (TaskStatus.REJECTED, TaskStatus.IN_PROGRESS),
    ],
)
def test_forbidden_transition(
    current: TaskStatus,
    new: TaskStatus,
) -> None:
    assert not can_transition(current, new)


def test_validate_transition_raises_forbidden_transition() -> None:
    with pytest.raises(ValueError, match="Недопустимый переход"):
        validate_transition(
            TaskStatus.CREATED,
            TaskStatus.COMPLETED,
        )


def test_validate_reason_accepts_text() -> None:
    validate_reason("Необходимо исправить замечания")


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_validate_reason_rejects_empty_reason(
    reason: str | None,
) -> None:
    with pytest.raises(ValueError, match="Необходимо указать причину"):
        validate_reason(reason)