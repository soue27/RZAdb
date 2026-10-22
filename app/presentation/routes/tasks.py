from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.access.service import AccessService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.application.work_items.service import WorkItemService
from app.domain.enums import (
    MaintenanceType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.task import Task
from app.domain.user import User
from app.presentation.auth.dependencies import (
    get_current_user,
    require_non_specialist,
)
from app.presentation.dependencies.services import (
    get_access_service,
    get_inspection_task_repository,
    get_inspection_task_service,
    get_task_repository,
    get_task_service,
    get_tree_service,
    get_work_item_service,
)

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_non_specialist)],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
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

INSPECTION_STATUS_LABELS = {
    TaskStatus.CREATED: "Создано",
    TaskStatus.ASSIGNED: "Назначено",
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.COMPLETED: "Выполнено",
    TaskStatus.UNDER_REVIEW: "На проверке",
    TaskStatus.CLOSED: "Закрыто",
    TaskStatus.REJECTED: "Отклонено",
}


def _default_task_return_url(
    *,
    urza_id: UUID,
    work_type: TaskWorkType,
) -> str:
    paths = {
        TaskWorkType.OTD: "",
        TaskWorkType.SETTINGS: "/settings",
        TaskWorkType.SCHEMES: "/schemas",
        TaskWorkType.MAINTENANCE: "/maintenance",
        TaskWorkType.PROGRAM: "/programs",
        TaskWorkType.INSTRUCTION: "/instruction",
    }

    return f"/objects/urza/{urza_id}{paths[work_type]}"


def _normalize_return_url(
    *,
    return_url: str | None,
    urza_id: UUID,
    work_type: TaskWorkType,
) -> str:
    default_url = _default_task_return_url(
        urza_id=urza_id,
        work_type=work_type,
    )

    if not return_url:
        return default_url

    if not return_url.startswith("/") or return_url.startswith("//"):
        return default_url

    return return_url


async def _task_create_form_response(
    *,
    request: Request,
    current_user: User,
    urza,
    urza_id: UUID | None,
    work_type: TaskWorkType | None,
    engineers: list,
    tree,
    return_url: str,
    error_message: str | None = None,
    deadline_at: str = "",
    maintenance_type: str = "",
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
            "work_type_label": WORK_TYPE_LABELS.get(
                work_type,
                "Не выбран",
            ),
            "engineers": engineers,
            "error_message": error_message,
            "deadline_at": deadline_at,
            "engineer_id": engineer_id,
            "description": description,
            "maintenance_types": list(MaintenanceType),
            "maintenance_type": maintenance_type,
            "tree": tree,
            "return_url": return_url,
        },
        status_code=status_code,
    )


async def _get_accessible_task(
    repository: TaskRepository,
    access_service: AccessService,
    current_user: User,
    task_id: UUID,
) -> Task:
    task = await repository.get_active_by_id(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено.",
        )

    has_access = (
        await access_service.can_access_urza(current_user.id, task.urza_id)
        if task.urza_id is not None
        else await access_service.can_access_substation(
            current_user.id, task.substation_id
        )
    )
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="Доступ к заданию запрещён.",
        )

    # Инженер может открывать только назначенные ему задания.
    if (
        current_user.role is UserRole.ENGINEER
        and task.assigned_to != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Задание не назначено этому инженеру.",
        )

    return task


def _task_context(
    task: Task,
    history: list,
    actions: set[str],
) -> dict:
    return {
        "task": task,
        "history": history,
        "actions": actions,
        "status_labels": TASK_STATUS_LABELS,
        "status_badges": TASK_STATUS_BADGES,
        "work_type_labels": WORK_TYPE_LABELS,
        "history_event_labels": HISTORY_EVENT_LABELS,
    }


async def _task_detail_context(
    *,
    task: Task,
    current_user: User,
    repository: TaskRepository,
    task_service: TaskService,
    tree_service: TreeService,
    error_message: str | None = None,
) -> dict:
    history = await repository.get_history(task.id)
    actions = await task_service.get_available_actions(
        task=task,
        actor_id=current_user.id,
    )
    tree = await tree_service.get_tree(user_id=current_user.id)

    program_result = None
    if task.work_type is TaskWorkType.PROGRAM:
        program_result = await repository.get_program_by_task_id(task.id)
        if program_result is not None and program_result.deleted_at is not None:
            program_result = None

    available_assignees = []
    if "reassign_task" in actions:
        available_assignees = await task_service.get_available_assignees(
            actor_id=current_user.id,
            urza_id=task.urza_id,
            substation_id=task.substation_id,
        )

    return {
        "current_user": current_user,
        "tree": tree,
        **_task_context(task, history, actions),
        "available_assignees": available_assignees,
        "program_result": program_result,
        "error_message": error_message,
    }


@router.get("/create")
async def get_task_create_form(
    request: Request,
    urza_id: UUID,
    work_type: TaskWorkType,
    current_user: Annotated[User, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    return_url: str | None = None,
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
        raise HTTPException(
            status_code=404,
            detail="URZA не найден.",
        )

    engineers = await task_service.get_available_assignees(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    tree = await tree_service.get_tree(
        user_id=current_user.id,
    )

    normalized_return_url = _normalize_return_url(
        return_url=return_url,
        urza_id=urza_id,
        work_type=work_type,
    )

    return await _task_create_form_response(
        request=request,
        current_user=current_user,
        urza=urza,
        urza_id=urza_id,
        work_type=work_type,
        engineers=engineers,
        tree=tree,
        return_url=normalized_return_url,
    )


@router.post("/create")
async def create_task(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    urza_id: Annotated[str, Form()] = "",
    work_type: Annotated[str, Form()] = "",
    engineer_id: Annotated[str, Form()] = "",
    deadline_at: Annotated[str, Form()] = "",
    maintenance_type: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    return_url: Annotated[str, Form()] = "",
):
    tree = await tree_service.get_tree(
        user_id=current_user.id,
    )

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
            tree=tree,
            return_url=return_url or "/tasks",
            error_message=(
                "Проверьте выбранный объект, тип работы и исполнителя."
            ),
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    normalized_return_url = _normalize_return_url(
        return_url=return_url,
        urza_id=parsed_urza_id,
        work_type=parsed_work_type,
    )

    if not await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=parsed_urza_id,
    ):
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=None,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=[],
            tree=tree,
            return_url=normalized_return_url,
            error_message=(
                "Пользователь не может выдавать задания для этого URZA."
            ),
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    urza = await access_service.urza_repository.get_by_id(
        parsed_urza_id,
    )

    if urza is None:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=None,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=[],
            tree=tree,
            return_url=normalized_return_url,
            error_message="URZA не найден.",
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
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
            tree=tree,
            return_url=normalized_return_url,
            error_message=str(exc),
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if parsed_engineer_id not in {
        engineer.id
        for engineer in engineers
    }:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=engineers,
            tree=tree,
            return_url=normalized_return_url,
            error_message=(
                "Выбранный исполнитель не является доступным "
                "активным инженером этого отделения."
            ),
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
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
            tree=tree,
            return_url=normalized_return_url,
            error_message="Укажите корректный срок выполнения.",
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
            engineer_id=engineer_id,
            description=description,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if parsed_deadline_at.tzinfo is None:
        parsed_deadline_at = parsed_deadline_at.astimezone()

    parsed_maintenance_type = None

    if parsed_work_type == TaskWorkType.MAINTENANCE:
        try:
            parsed_maintenance_type = MaintenanceType(maintenance_type)
        except ValueError:
            return await _task_create_form_response(
                request=request,
                current_user=current_user,
                urza=urza,
                urza_id=parsed_urza_id,
                work_type=parsed_work_type,
                engineers=engineers,
                tree=tree,
                return_url=normalized_return_url,
                error_message="Укажите вид технического обслуживания.",
                deadline_at=deadline_at,
                maintenance_type=maintenance_type,
                engineer_id=engineer_id,
                description=description,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    try:
        task = await task_service.create_task(
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            created_by=current_user.id,
            description=description.strip() or None,
            deadline_at=parsed_deadline_at,
            maintenance_type=parsed_maintenance_type,
        )
    except (PermissionError, ValueError) as exc:
        return await _task_create_form_response(
            request=request,
            current_user=current_user,
            urza=urza,
            urza_id=parsed_urza_id,
            work_type=parsed_work_type,
            engineers=engineers,
            tree=tree,
            return_url=normalized_return_url,
            error_message=str(exc),
            deadline_at=deadline_at,
            maintenance_type=maintenance_type,
            engineer_id=engineer_id,
            description=description,
            status_code=(
                403
                if isinstance(exc, PermissionError)
                else 400
            ),
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
    work_item_service: Annotated[
        WorkItemService,
        Depends(get_work_item_service),
    ],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    inspection_repository: Annotated[
        InspectionTaskRepository,
        Depends(get_inspection_task_repository),
        ],
    inspection_service: Annotated[
        InspectionTaskService,
        Depends(get_inspection_task_service),
    ],
    access_service: Annotated[AccessService, Depends(get_access_service)],
):
    work_items = await work_item_service.list_for_user(current_user.id)
    inspection_tasks = []

    reviewed_inspection_ids = set()
    if current_user.role is UserRole.SUPERADMIN:
        reviewed_inspection_ids = (
            await inspection_repository.list_reviewed_task_ids(
                current_user.id,
            )
        )

    for task in await inspection_repository.list_active():
        if not await access_service.can_access_substation(
            current_user.id, task.substation_id
        ):
            continue

        if (
            current_user.role is UserRole.ENGINEER
            and task.assigned_to != current_user.id
        ):
            continue

        if current_user.role is UserRole.SUPERADMIN:
            is_author = task.created_by == current_user.id
            is_assignee = task.assigned_to == current_user.id
            is_reviewer = task.id in reviewed_inspection_ids

            if not (is_author or is_assignee or is_reviewer):
                continue

        inspection_tasks.append(task)

    all_items = []

    for item in work_items:
        all_items.append({
            "tab": item.tab,
            "title": item.title,
            "item_type": item.item_type,
            "parent": item.parent,
            "author": item.author,
            "assignee": item.assignee,
            "created_at": item.created_at,
            "status": item.status,
            "status_class": item.status_class,
            "url": item.url,
            "can_approve": item.can_approve,
        })

    for task in inspection_tasks:
        if task.status is TaskStatus.UNDER_REVIEW:
            tab = "review"
        elif task.status is TaskStatus.CLOSED:
            tab = "completed"
        else:
            tab = "work"

        can_approve = (
            await inspection_service.can_review(
                task.id,
                actor_id=current_user.id,
            )
        )

        all_items.append({
            "tab": tab,
            "title": f"Осмотр ПС · {task.substation.dispatch_name}",
            "item_type": "Задача осмотра",
            "parent": task.substation.dispatch_name,
            "author": (
                task.created_by_user.full_name
                if task.created_by_user else "—"
            ),
            "assignee": (
                task.assigned_to_user.full_name
                if task.assigned_to_user else "Не назначен"
            ),
            "created_at": task.created_at,
            "status": INSPECTION_STATUS_LABELS[task.status],
            "status_class": TASK_STATUS_BADGES[task.status],
            "url": f"/objects/substation/inspection-tasks/{task.id}",
            "can_approve": can_approve,
        })

    all_items.sort(
        key=lambda item: item["created_at"],
        reverse=True,
    )


    tree = await tree_service.get_tree(
        user_id=current_user.id,
    )

    return templates.TemplateResponse(
        request=request,
        name="tasks/list.html",
        context={
            "current_user": current_user,
            "tree": tree,
            "all_items": all_items,
            "inspection_status_labels": INSPECTION_STATUS_LABELS,
            "status_badges": TASK_STATUS_BADGES,
            "can_approve_items": (
                    current_user.role is UserRole.MANAGER
                    and bool(tree)
            ),
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
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user,
        task_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="tasks/detail.html",
        context=await _task_detail_context(
            task=task,
            current_user=current_user,
            repository=repository,
            task_service=task_service,
            tree_service=tree_service,
        ),
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
    tree_service: TreeService,
    action: str,
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user,
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
        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if request.headers.get("HX-Request") == "true"
                else "tasks/detail.html"
            ),
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
                error_message=str(exc),
            ),
            status_code=(
                200
                if request.headers.get("HX-Request") == "true"
                else 403
            ),
        )

    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if request.headers.get("HX-Request") == "true"
                else "tasks/detail.html"
            ),
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
                error_message=str(exc),
            ),
            status_code=(
                200
                if request.headers.get("HX-Request") == "true"
                else 400
            ),
        )

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="tasks/_detail_content.html",
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
            ),
        )

    return RedirectResponse(
        url=f"/tasks/{task_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )



async def _run_executor_action(
    *,
    request: Request,
    task_id: UUID,
    current_user: User,
    repository: TaskRepository,
    access_service: AccessService,
    task_service: TaskService,
    tree_service: TreeService,
    action: str,
    reason: str | None = None,
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user,
        task_id,
    )

    try:
        if action == "accept_task":
            await task_service.accept_task(
                task=task,
                actor_id=current_user.id,
            )
        elif action == "complete_task":
            await task_service.complete_task(
                task=task,
                actor_id=current_user.id,
            )
        elif action == "reject_task":
            await task_service.reject_task(
                task=task,
                actor_id=current_user.id,
                reason=reason or "",
            )
        else:
            raise ValueError(f"Неизвестное действие: {action}")

    except (PermissionError, ValueError) as exc:
        is_htmx = request.headers.get("HX-Request") == "true"

        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if is_htmx
                else "tasks/detail.html"
            ),
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
                error_message=str(exc),
            ),
            status_code=(
                200
                if is_htmx
                else (
                    403
                    if isinstance(exc, PermissionError)
                    else 400
                )
            ),
        )

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="tasks/_detail_content.html",
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
            ),
        )

    return RedirectResponse(
        url=f"/tasks/{task_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{task_id}/accept")
async def accept_task(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    return await _run_executor_action(
        request=request,
        task_id=task_id,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        tree_service=tree_service,
        action="accept_task",
    )


@router.post("/{task_id}/complete")
async def complete_task(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    return await _run_executor_action(
        request=request,
        task_id=task_id,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        tree_service=tree_service,
        action="complete_task",
    )


@router.post("/{task_id}/reject")
async def reject_task(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    reason: Annotated[str, Form()],
):
    return await _run_executor_action(
        request=request,
        task_id=task_id,
        current_user=current_user,
        repository=repository,
        access_service=access_service,
        task_service=task_service,
        tree_service=tree_service,
        action="reject_task",
        reason=reason,
    )



@router.post("/{task_id}/submit-for-review")
async def submit_task_for_review(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
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
        tree_service=tree_service,
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
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
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
        tree_service=tree_service,
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
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
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
        tree_service=tree_service,
        action="return_for_revision",
    )



@router.post("/{task_id}/reassign")
async def reassign_task(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    engineer_id: Annotated[str, Form()],
):
    task = await _get_accessible_task(
        repository,
        access_service,
        current_user,
        task_id,
    )

    try:
        if not await task_service.can_issue_task(
            actor_id=current_user.id,
            urza_id=task.urza_id,
            substation_id=task.substation_id,
        ):
            raise PermissionError(
                "Пользователь не может переназначать это задание."
            )

        engineers = await task_service.get_available_assignees(
            actor_id=current_user.id,
            urza_id=task.urza_id,
            substation_id=task.substation_id,
        )

        parsed_engineer_id = UUID(engineer_id)
        if parsed_engineer_id not in {engineer.id for engineer in engineers}:
            raise ValueError(
                "Выбранный исполнитель не является доступным "
                "активным инженером этого предприятия."
            )

        await task_service.reassign_task(
            task=task,
            assigned_to=parsed_engineer_id,
            actor_id=current_user.id,
        )

    except (PermissionError, ValueError) as exc:
        is_htmx = request.headers.get("HX-Request") == "true"
        return templates.TemplateResponse(
            request=request,
            name=(
                "tasks/_detail_content.html"
                if is_htmx
                else "tasks/detail.html"
            ),
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
                error_message=str(exc),
            ),
            status_code=(
                200
                if is_htmx
                else 403 if isinstance(exc, PermissionError) else 400
            ),
        )

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="tasks/_detail_content.html",
            context=await _task_detail_context(
                task=task,
                current_user=current_user,
                repository=repository,
                task_service=task_service,
                tree_service=tree_service,
            ),
        )

    return RedirectResponse(
        url=f"/tasks/{task_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
