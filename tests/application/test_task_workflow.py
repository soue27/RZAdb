import pytest

from app.application.tasks.workflow import (
    can_transition,
    validate_reason,
    validate_transition,
)
from app.domain.enums import TaskStatus


def test_allowed_task_transitions() -> None:
    assert can_transition(
        TaskStatus.CREATED,
        TaskStatus.ASSIGNED,
    )

    assert can_transition(
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
    )

    assert can_transition(
        TaskStatus.ASSIGNED,
        TaskStatus.REJECTED,
    )

    assert can_transition(
        TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED,
    )

    assert can_transition(
        TaskStatus.COMPLETED,
        TaskStatus.UNDER_REVIEW,
    )

    assert can_transition(
        TaskStatus.UNDER_REVIEW,
        TaskStatus.CLOSED,
    )

    assert can_transition(
        TaskStatus.UNDER_REVIEW,
        TaskStatus.IN_PROGRESS,
    )


def test_forbidden_task_transitions() -> None:
    assert not can_transition(
        TaskStatus.CREATED,
        TaskStatus.IN_PROGRESS,
    )

    assert not can_transition(
        TaskStatus.ASSIGNED,
        TaskStatus.COMPLETED,
    )

    assert not can_transition(
        TaskStatus.IN_PROGRESS,
        TaskStatus.CLOSED,
    )

    assert not can_transition(
        TaskStatus.CLOSED,
        TaskStatus.IN_PROGRESS,
    )

    assert not can_transition(
        TaskStatus.REJECTED,
        TaskStatus.ASSIGNED,
    )


def test_validate_transition_raises_forbidden_transition() -> None:
    with pytest.raises(ValueError, match="Недопустимый переход"):
        validate_transition(
            TaskStatus.CREATED,
            TaskStatus.CLOSED,
        )


def test_validate_transition_accepts_allowed_transition() -> None:
    validate_transition(
        TaskStatus.CREATED,
        TaskStatus.ASSIGNED,
    )


def test_reason_is_required() -> None:
    with pytest.raises(ValueError, match="Причина обязательна"):
        validate_reason(None)

    with pytest.raises(ValueError, match="Причина обязательна"):
        validate_reason("")

    with pytest.raises(ValueError, match="Причина обязательна"):
        validate_reason("   ")


def test_reason_is_valid() -> None:
    validate_reason("Оборудование требует дополнительной проверки.")