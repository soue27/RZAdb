from typing import Annotated
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.access.service import AccessService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.domain.enums import TaskStatus, TaskWorkType
from app.domain.task import Task
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_access_service,
    get_task_repository,
    get_task_service,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
templates = Jinja2Templates(directory="app/presentation/templates")


async def _task_create_form_response(
    *,
    request: Request,
    current_user: User,
    urza,
    urza_id: UUID | None,
    work_type: TaskWorkType | None,
    engineers: list,
    error_message: str | None = None,
    deadline_at: str = "",
    engineer_id: str = "",
    description: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="tasks/create.html",
        context={
            "current_user": current_user,
            "urza": urza,
            "urza_id": urza_id,
            "work_type": work_type,
            "work_type_label": WORK_TYPE_LABELS.get(work_type, "Не выбран"),
            "engineers": engineers,
            "error_message": error_message,
            "deadline_at": deadline_at,
            "engineer_id": engineer_id,
            "description": description,
        },
        status_code=status_code,
    )

TASK_STATUS_LABELS = {
    TaskStatus.CREATED: "Создано",
    TaskStatus.ASSIGNED: "Назначено",
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.COMPLETED: "Выполнено",
    TaskStatus.UNDER_REVIEW: "На согласовании",
    TaskStatus.CLOSED: "Закрыто",
    TaskStatus.REJECTED: "Отклонено",
}
TASK_STATUS_BADGES = {
    TaskStatus.CREATED: "text-bg-secondary",
    TaskStatus.ASSIGNED: "text-bg-info",
    TaskStatus.IN_PROGRESS: "text-bg-primary",
    TaskStatus.COMPLETED: "text-bg-warning",
    TaskStatus.UNDER_REVIEW: "text-bg-warning",
    TaskStatus.CLOSED: "text-bg-success",
    TaskStatus.REJECTED: "text-bg-danger",
}
WORK_TYPE_LABELS = {
    TaskWorkType.OTD: "ОТД",
    TaskWorkType.SETTINGS: "Уставки",
    TaskWorkType.SCHEMES: "Схемы",
    TaskWorkType.MAINTENANCE: "Техническое обслуживание",
    TaskWorkType.PROGRAM: "Программы",
    TaskWorkType.INSTRUCTION: "Инструкция",
}
HISTORY_EVENT_LABELS = {
    "created": "Задание создано",
    "assigned": "Задание назначено",
    "accepted": "Задание принято",
    "started": "Работа начата",
    "completed": "Работа завершена исполнителем",
    "sent_to_review": "Направлено на согласование",
    "review_approved": "Задание закрыто руководителем",
    "review_rejected": "Возвращено на доработку",
    "rejected": "Отказ от задания",
    "reassigned": "Задание переназначено",
}


async def _get_accessible_task(
    repository: TaskRepository,
    access_service: AccessService,
    user_id: UUID,
    task_id: UUID,
) -> Task:
    task = await repository.get_active_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    if not await access_service.can_access_urza(user_id, task.urza_id):
        raise HTTPException(
            status_code=403,
            detail="Доступ к заданию запрещён.",
        )
    return task


def _task_context(task: Task, history: list, actions: set[str]) -> dict:
    return {
        "task": task,
        "history": history,
        "actions": actions,
        "status_labels": TASK_STATUS_LABELS,
        "status_badges": TASK_STATUS_BADGES,
        "work_type_labels": WORK_TYPE_LABELS,
        "history_event_labels": HISTORY_EVENT_LABELS,
    }


@router.get("/create")
async def get_task_create_form(
    request: Request,
    urza_id: UUID,
    work_type: TaskWorkType,
    current_user: Annotated[User, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
):
    if not await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь не может выдавать задания для этого URZA.",
        )

    urza = await access_service.urza_repository.get_by_id(urza_id)
    if urza is None:
        raise HTTPException(status_code=404, detail="URZA не найден.")

    engineers = await task_service.get_available_assignees(
        actor_id=current_user.id,
        urza_id=urza_id,
    )
    return await _task_create_form_response(
        request=request,
        current_user=current_user,
        urza=urza,
        urza_id=urza_id,
        work_type=work_type,
        engineers=engineers,
    )


@router.post("/create")
async def create_task(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    urza_id: Annotated[str, Form()] = "",
    work_type: Annotated[str, Form()] = "",
    engineer_id: Annotated[str, Form()] = "",
    deadline_at: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
):
    try:
        parsed_urza_id = UUID(urza_id)
        parsed_work_type = TaskWorkType(work_type)
        parsed_engineer_id = UUID(engineer_id)
    except ValueError:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=None,
            urza_id=None,
            work_type=None,
            engineers=[],
            error_message="Проверьте выбранный объект, тип работы и исполнителя.",
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=parsed_urza_id,
    ):
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=None,
            urza_id=None,
            work_type=parsed_work_type,
            engineers=[],
            error_message="Пользователь не может выдавать задания для этого URZA.",
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    urza = await access_service.urza_repository.get_by_id(parsed_urza_id)
    if urza is None:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=None,
            work_type=parsed_work_type,
            engineers=[],
            error_message="URZA не найден.",
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        engineers = await task_service.get_available_assignees(
            actor_id=current_user.id,
            urza_id=parsed_urza_id,
        )
    except PermissionError as exc:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=[],
            error_message=str(exc),
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if parsed_engineer_id not in {engineer.id for engineer in engineers}:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=engineers,
            error_message="Выбранный исполнитель не является доступным активным инженером этого отделения.",
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_deadline_at = datetime.fromisoformat(deadline_at)
    except ValueError:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=engineers,
            error_message="Укажите корректный срок выполнения.",
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if parsed_deadline_at.tzinfo is None:
        parsed_deadline_at = parsed_deadline_at.astimezone()

    try:
        task = await task_service.create_task(
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            created_by=current_user.id,
            description=description.strip() or None,
            deadline_at=parsed_deadline_at,
        )
    except (PermissionError, ValueError) as exc:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=engineers,
            error_message=str(exc),
            deadline_at=deadline_at,
            engineer_id=engineer_id,
            description=description,
            status_code=403 if isinstance(exc, PermissionError) else 400,
        )

    await task_service.assign_task(
        task=task,
        assigned_to=parsed_engineer_id,
        actor_id=current_user.id,
    )

    return RedirectResponse(
        url=f"/tasks/{task.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("")
async def get_tasks(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    visible_tasks = []
    actions_by_task = {}
    for task in await repository.list_active():
        if not await access_service.can_access_urza(current_user.id, task.urza_id):
            continue
        visible_tasks.append(task)
        actions_by_task[task.id] = await task_service.get_available_actions(
            task=task,
            actor_id=current_user.id,
        )

    return templates.TemplateResponse(
        request=request,
        name="tasks/list.html",
        context={
            "current_user": current_user,
            "tasks": visible_tasks,
            "actions_by_task": actions_by_task,
            "status_labels": TASK_STATUS_LABELS,
            "status_badges": TASK_STATUS_BADGES,
            "work_type_labels": WORK_TYPE_LABELS,
        },
    )


@router.get("/{task_id}")
async def get_task_detail(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user.id,
        task_id,
    )
    history = await repository.get_history(task.id)
    actions = await task_service.get_available_actions(
        task=task,
        actor_id=current_user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="tasks/detail.html",
        context={
            "current_user": current_user,
            **_task_context(task, history, actions),
            "error_message": None,
        },
    )


async def _run_review_action(
    *,
    request: Request,
    task_id: UUID,
    comment: str | None,
    current_user: User,
    repository: TaskRepository,
    access_service: AccessService,
    task_service: TaskService,
    action: str,
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user.id,
        task_id,
    )
    try:
        if action == "submit_for_review":
            await task_service.submit_for_review(
                task=task,
                actor_id=current_user.id,
                comment=comment,
            )
        elif action == "close_task":
            await task_service.close_task(
                task=task,
                actor_id=current_user.id,
                comment=comment,
            )
        else:
            await task_service.return_for_revision(
                task=task,
                actor_id=current_user.id,
                comment=comment,
            )
    except PermissionError as exc:
        history = await repository.get_history(task.id)
        actions = await task_service.get_available_actions(
            task=task,
            actor_id=current_user.id,
        )
        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if request.headers.get("HX-Request") == "true"
                else "tasks/detail.html"
            ),
            context={
                "current_user": current_user,
                **_task_context(task, history, actions),
                "error_message": str(exc),
            },
            status_code=(
                200 if request.headers.get("HX-Request") == "true" else 403
            ),
        )
    except ValueError as exc:
        history = await repository.get_history(task.id)
        actions = await task_service.get_available_actions(
            task=task,
            actor_id=current_user.id,
        )
        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if request.headers.get("HX-Request") == "true"
                else "tasks/detail.html"
            ),
            context={
                "current_user": current_user,
                **_task_context(task, history, actions),
                "error_message": str(exc),
            },
            status_code=(
                200 if request.headers.get("HX-Request") == "true" else 400
            ),
        )

    if request.headers.get("HX-Request") == "true":
        history = await repository.get_history(task.id)
        actions = await task_service.get_available_actions(
            task=task,
            actor_id=current_user.id,
        )
        return templates.TemplateResponse(
            request=request,
            name="tasks/_detail_content.html",
            context={
                "current_user": current_user,
                **_task_context(task, history, actions),
                "error_message": None,
            },
        )

    return RedirectResponse(
        url=f"/tasks/{task_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{task_id}/submit-for-review")
async def submit_task_for_review(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    comment: Annotated[str | None, Form()] = None,
):
    return await _run_review_action(
        request=request,
        task_id=task_id,
        comment=comment,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        action="submit_for_review",
    )


@router.post("/{task_id}/close")
async def close_task(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    comment: Annotated[str | None, Form()] = None,
):
    return await _run_review_action(
        request=request,
        task_id=task_id,
        comment=comment,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        action="close_task",
    )


@router.post("/{task_id}/return-for-revision")
async def return_task_for_revision(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    comment: Annotated[str | None, Form()] = None,
):
    return await _run_review_action(
        request=request,
        task_id=task_id,
        comment=comment,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        action="return_for_revision",
    )
