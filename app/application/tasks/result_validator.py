from app.domain.enums import MaintenanceType, TaskWorkType


def validate_task_result(
    *,
    work_type: TaskWorkType,
    maintenance_type: MaintenanceType | None,
    has_result: bool,
) -> None:
    """Проверяет наличие обязательного результата перед завершением задачи."""

    if work_type == TaskWorkType.MAINTENANCE:
        if maintenance_type is None:
            raise ValueError(
                "Для задания на ТО необходимо указать maintenance_type."
            )

        if not has_result:
            raise ValueError(
                "Для завершения задания на ТО необходимо создать результат."
            )