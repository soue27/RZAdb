from app.domain.enums import TaskStatus


# Описываем только допустимые переходы между статусами.
# Это держит правила workflow отдельно от БД и HTTP-слоя.
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset(
        {
            TaskStatus.ASSIGNED,
        }
    ),
    TaskStatus.ASSIGNED: frozenset(
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.REJECTED,
        }
    ),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.COMPLETED,
        }
    ),
    TaskStatus.COMPLETED: frozenset(
        {
            TaskStatus.UNDER_REVIEW,
        }
    ),
    TaskStatus.UNDER_REVIEW: frozenset(
        {
            TaskStatus.CLOSED,
            TaskStatus.IN_PROGRESS,
        }
    ),
    TaskStatus.REJECTED: frozenset(),
    TaskStatus.CLOSED: frozenset(),
}


def can_transition(
    current_status: TaskStatus,
    new_status: TaskStatus,
) -> bool:
    """Возвращает True, если переход между статусами разрешён."""
    return new_status in ALLOWED_TRANSITIONS.get(current_status, frozenset())


def validate_transition(
    current_status: TaskStatus,
    new_status: TaskStatus,
) -> None:
    """Проверяет переход и выбрасывает ошибку при нарушении workflow."""
    if not can_transition(current_status, new_status):
        raise ValueError(
            f"Недопустимый переход задачи: "
            f"{current_status.value} -> {new_status.value}"
        )


def validate_reason(reason: str | None) -> None:
    """Проверяет обязательную причину для отказа или возврата на доработку."""
    if not reason or not reason.strip():
        raise ValueError("Причина обязательна.")