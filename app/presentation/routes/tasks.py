from typing import Annotated
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
