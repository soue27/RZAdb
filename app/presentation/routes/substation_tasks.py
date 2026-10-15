from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.objects.exceptions import ObjectAccessDeniedError, ObjectNotFoundError
from app.application.objects.service import ObjectService
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.domain.enums import TaskWorkType
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_object_service, get_task_service, get_tree_service

router = APIRouter(prefix="/tasks/substation", tags=["tasks"])
templates = Jinja2Templates(directory="app/presentation/templates")
ALLOWED_TYPES = {TaskWorkType.INSTRUCTION, TaskWorkType.SCHEMES}


async def _substation(objects: ObjectService, user: User, substation_id: UUID):
    try:
        return await objects.get_object(
            user_id=user.id, object_type="substation", object_id=substation_id
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к подстанции запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc


@router.get("/create")
async def new_substation_task(
    request: Request,
    substation_id: UUID,
    work_type: TaskWorkType,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    if work_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Тип задания для подстанции не поддерживается.")
    substation = await _substation(objects, current_user, substation_id)
    try:
        engineers = await service.get_available_assignees(
            actor_id=current_user.id, substation_id=substation_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    tree = await tree_service.get_tree(user_id=current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="tasks/substation_create.html",
        context={
            "substation": substation,
            "substation_id": substation_id,
            "work_type": work_type,
            "work_type_label": "Инструкция РЗА подстанции" if work_type is TaskWorkType.INSTRUCTION else "Схема селективности",
            "engineers": engineers,
            "tree": tree,
            "error_message": None,
            "deadline_at": "",
            "description": "",
            "engineer_id": "",
        },
    )


@router.post("/create")
async def create_substation_task(
    request: Request,
    substation_id: Annotated[UUID, Form()],
    work_type: Annotated[TaskWorkType, Form()],
    engineer_id: Annotated[UUID, Form()],
    deadline_at: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    description: Annotated[str, Form()] = "",
):
    if work_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Тип задания для подстанции не поддерживается.")
    substation = await _substation(objects, current_user, substation_id)
    try:
        engineers = await service.get_available_assignees(
            actor_id=current_user.id, substation_id=substation_id
        )
        if engineer_id not in {engineer.id for engineer in engineers}:
            raise ValueError("Выбранный исполнитель недоступен для этой подстанции.")
        deadline = datetime.fromisoformat(deadline_at)
        if deadline.tzinfo is None:
            deadline = deadline.astimezone()
        task = await service.create_task(
            substation_id=substation_id,
            work_type=work_type,
            created_by=current_user.id,
            deadline_at=deadline,
            description=description.strip() or None,
        )
        await service.assign_task(
            task=task, assigned_to=engineer_id, actor_id=current_user.id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        engineers = await service.get_available_assignees(
            actor_id=current_user.id, substation_id=substation_id
        )
        return templates.TemplateResponse(
            request=request,
            name="tasks/substation_create.html",
            status_code=400,
            context={
                "substation": substation, "substation_id": substation_id,
                "work_type": work_type,
                "work_type_label": "Инструкция РЗА подстанции" if work_type is TaskWorkType.INSTRUCTION else "Схема селективности",
                "engineers": engineers,
                "tree": await tree_service.get_tree(user_id=current_user.id),
                "error_message": str(exc), "deadline_at": deadline_at,
                "description": description, "engineer_id": str(engineer_id),
            },
        )
    tab = "instructions" if work_type is TaskWorkType.INSTRUCTION else "selectivity-schemes"
    return RedirectResponse(
        f"/objects/substation/{substation_id}?tab={tab}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
