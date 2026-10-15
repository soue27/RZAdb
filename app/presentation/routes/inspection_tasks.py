from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.objects.exceptions import ObjectAccessDeniedError, ObjectNotFoundError
from app.application.objects.service import ObjectService
from app.application.tree.service import TreeService
from app.domain.enums import UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service, get_inspection_task_service, get_object_service,
    get_inspection_task_repository,
)

router = APIRouter(prefix="/objects/substation", tags=["inspection tasks"])
templates = Jinja2Templates(directory="app/presentation/templates")


async def _accessible_task(objects: ObjectService, repository: InspectionTaskRepository, user: User, task_id: UUID):
    task = await repository.get_active_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача осмотра не найдена.")
    try:
        await objects.get_object(user_id=user.id, object_type="substation", object_id=task.substation_id)
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к подстанции запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc
    return task


async def _done(request: Request, substation_id: UUID):
    target = f"/objects/substation/{substation_id}?tab=inspections"
    if request.headers.get("HX-Request") == "true":
        from fastapi.responses import Response
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{substation_id}/inspection-tasks")
async def create_inspection_task(
    request: Request, substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    assignee_id: Annotated[str, Form()] = "",
):
    try:
        await objects.get_object(user_id=current_user.id, object_type="substation", object_id=substation_id)
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к подстанции запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc
    if current_user.role is not UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Создавать задачи осмотра может только MANAGER.")
    try:
        parsed_assignee = UUID(assignee_id) if assignee_id else None
        if assignee_id:
            substation_record = await service.substation_repository.get_by_id(substation_id)
            if substation_record is None:
                raise ValueError("Подстанция не найдена.")
            engineers = await service.user_repository.get_active_inspection_assignees_by_enterprise(substation_record.enterprise_id)
            if parsed_assignee not in {engineer.id for engineer in engineers}:
                raise ValueError("Исполнитель не относится к подразделению подстанции.")

        await service.create_and_assign(
            substation_id=substation_id,
            actor_id=current_user.id,
            assignee_id=parsed_assignee,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, substation_id)


@router.post("/inspection-tasks/{task_id}/assign")
async def assign_inspection_task(
    request: Request, task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
    assignee_id: Annotated[UUID, Form()],
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    substation = task.substation
    assignees = await service.user_repository.get_active_inspection_assignees_by_enterprise(substation.enterprise_id)
    if assignee_id not in {user.id for user in assignees}:
        raise HTTPException(status_code=400, detail="Выбранный исполнитель недоступен.")
    try:
        await service.assign(task_id, actor_id=current_user.id, assignee_id=assignee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id)


@router.post("/inspection-tasks/{task_id}/accept")
async def accept_inspection_task(
    request: Request, task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    try:
        await service.accept(task_id, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id)


async def _upload(file_service: FileService, user: User, upload: UploadFile | None):
    if upload is None or not upload.filename:
        return None
    filename = upload.filename
    return await file_service.upload(
        actor_id=user.id, content=await upload.read(), original_name=filename,
        display_name=filename,
        extension=("." + filename.rsplit(".", 1)[1]) if "." in filename else "",
        mime_type=upload.content_type or "application/octet-stream",
    )


@router.post("/inspection-tasks/{task_id}/complete")
async def complete_inspection_task(
    request: Request, task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
    files: Annotated[FileService, Depends(get_file_service)],
    inspection_date: Annotated[date, Form()], remarks: Annotated[str, Form()],
    scan_file: Annotated[UploadFile | None, File()] = None,
    editable_file: Annotated[UploadFile | None, File()] = None,
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    try:
        await service.validate_completion(
            task_id, actor_id=current_user.id, remarks=remarks
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scan = await _upload(files, current_user, scan_file)
    editable = await _upload(files, current_user, editable_file)
    try:
        await service.complete(
            task_id, actor_id=current_user.id, inspection_date=inspection_date,
            remarks=remarks, scan_file_id=scan.id if scan else None,
            editable_file_id=editable.id if editable else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id)


@router.post("/inspection-tasks/{task_id}/send-to-review")
async def send_inspection_for_review(
    request: Request, task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    try:
        await service.send_to_review(task_id, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id)


@router.post("/inspection-tasks/{task_id}/review")
async def review_inspection(
    request: Request, task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
    approve: Annotated[bool, Form()], reason: Annotated[str, Form()] = "",
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    try:
        await service.review(task_id, actor_id=current_user.id, approve=approve, reason=reason or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id)
