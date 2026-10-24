import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.tree.service import TreeService
from app.domain.enums import UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_inspection_task_repository,
    get_inspection_task_service,
    get_object_service,
    get_tree_service,
)
from app.presentation.file_uploads import read_upload_content
from app.application.files.validation import FileUploadValidationError

router = APIRouter(prefix="/objects/substation", tags=["inspection tasks"])
logger = logging.getLogger(__name__)
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


async def _done(request: Request, substation_id: UUID, task_id: UUID):
    target = f"/objects/substation/inspection-tasks/{task_id}"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


async def _render_create_form(
    request: Request,
    *,
    substation_id: UUID,
    current_user: User,
    service: InspectionTaskService,
    tree: TreeService,
    assignee_id: str = "",
    error_message: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    substation = await service.substation_repository.get_by_id(substation_id)
    if substation is None:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.")
    assignees = await service.user_repository.get_active_inspection_assignees_by_enterprise(
        substation.enterprise_id
    )
    return templates.TemplateResponse(
        request=request,
        name="tasks/inspection_create.html",
        context={
            "current_user": current_user,
            "tree": await tree.get_tree(user_id=current_user.id),
            "substation": substation,
            "substation_id": substation_id,
            "inspection_assignees": assignees,
            "assignee_id": assignee_id,
            "error_message": error_message,
        },
        status_code=status_code,
    )


@router.get("/{substation_id}/inspection-tasks/new")
async def new_inspection_task(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
):
    try:
        await objects.get_object(
            user_id=current_user.id, object_type="substation", object_id=substation_id
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к подстанции запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc
    if current_user.role is not UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Создавать задачи осмотра может только MANAGER.")
    return await _render_create_form(
        request,
        substation_id=substation_id,
        current_user=current_user,
        service=service,
        tree=tree,
    )


@router.get("/inspection-tasks/{task_id}")
async def inspection_task_detail(
    request: Request,
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    repository: Annotated[InspectionTaskRepository, Depends(get_inspection_task_repository)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
):
    task = await _accessible_task(objects, repository, current_user, task_id)
    can_manage = current_user.role is UserRole.MANAGER
    assignees = (
        await service.user_repository.get_active_inspection_assignees_by_enterprise(
            task.substation.enterprise_id
        )
        if can_manage else []
    )
    from app.domain.enums import TaskStatus
    return templates.TemplateResponse(
        request=request,
        name="tasks/inspection_detail.html",
        context={
            "current_user": current_user,
            "tree": await tree.get_tree(user_id=current_user.id),
            "task": task,
            "history": await repository.get_history(task.id),
            "inspection_assignees": assignees,
            "can_manage_inspections": can_manage,
            "error_message": getattr(request.state, "inspection_error_message", None),
            "form_values": getattr(request.state, "inspection_form_values", {}),
            "status_labels": {
                TaskStatus.CREATED: "Создано", TaskStatus.ASSIGNED: "Назначено",
                TaskStatus.IN_PROGRESS: "В работе", TaskStatus.COMPLETED: "Выполнено",
                TaskStatus.UNDER_REVIEW: "На проверке", TaskStatus.CLOSED: "Закрыто",
                TaskStatus.REJECTED: "Отклонено",
            },
            "status_badges": {
                TaskStatus.CREATED: "text-bg-secondary", TaskStatus.ASSIGNED: "text-bg-info",
                TaskStatus.IN_PROGRESS: "text-bg-primary", TaskStatus.COMPLETED: "text-bg-warning",
                TaskStatus.UNDER_REVIEW: "text-bg-warning", TaskStatus.CLOSED: "text-bg-success",
                TaskStatus.REJECTED: "text-bg-danger",
            },
        },
    )


@router.post("/{substation_id}/inspection-tasks")
async def create_inspection_task(
    request: Request, substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[InspectionTaskService, Depends(get_inspection_task_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
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

        task = await service.create_and_assign(
            substation_id=substation_id,
            actor_id=current_user.id,
            assignee_id=parsed_assignee,
        )
    except PermissionError as exc:
        return await _render_create_form(
            request,
            substation_id=substation_id,
            current_user=current_user,
            service=service,
            tree=tree,
            assignee_id=assignee_id,
            error_message=str(exc),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except ValueError as exc:
        return await _render_create_form(
            request,
            substation_id=substation_id,
            current_user=current_user,
            service=service,
            tree=tree,
            assignee_id=assignee_id,
            error_message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await _done(request, substation_id, task.id)


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
    if current_user.role is not UserRole.MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Назначать исполнителя может только MANAGER.",
        )
    substation = task.substation
    assignees = await service.user_repository.get_active_inspection_assignees_by_enterprise(substation.enterprise_id)
    if assignee_id not in {user.id for user in assignees}:
        raise HTTPException(status_code=400, detail="Выбранный исполнитель недоступен.")
    try:
        await service.assign(task_id, actor_id=current_user.id, assignee_id=assignee_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id, task.id)


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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id, task.id)


async def _upload(file_service: FileService, user: User, upload: UploadFile | None):
    if upload is None or not upload.filename:
        return None
    filename = upload.filename
    return await file_service.upload(
        actor_id=user.id,
        content=await read_upload_content(upload),
        original_name=filename,
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
    tree: Annotated[TreeService, Depends(get_tree_service)],
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
    except (PermissionError, ValueError) as exc:
        request.state.inspection_error_message = str(exc)
        request.state.inspection_form_values = {
            "inspection_date": inspection_date.isoformat(), "remarks": remarks
        }
        response = await inspection_task_detail(
            request, task_id, current_user, objects, repository, service, tree
        )
        response.status_code = (
            status.HTTP_403_FORBIDDEN
            if isinstance(exc, PermissionError)
            else status.HTTP_400_BAD_REQUEST
        )
        return response


    uploaded_files = []

    try:
        scan = await _upload(files, current_user, scan_file)
        if scan is not None:
            uploaded_files.append(scan)

        editable = await _upload(files, current_user, editable_file)
        if editable is not None:
            uploaded_files.append(editable)

        await service.complete(
            task_id,
            actor_id=current_user.id,
            inspection_date=inspection_date,
            remarks=remarks,
            scan_file_id=scan.id if scan else None,
            editable_file_id=editable.id if editable else None,
        )

    except FileUploadValidationError as exc:
        for uploaded in uploaded_files:
            try:
                await files.archive(
                    file_id=uploaded.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки "
                    "валидации при завершении осмотра: file_id=%s",
                    uploaded.id,
                )

        request.state.inspection_error_message = str(exc)
        request.state.inspection_form_values = {
            "inspection_date": inspection_date.isoformat(),
            "remarks": remarks,
        }
        response = await inspection_task_detail(
            request,
            task_id,
            current_user,
            objects,
            repository,
            service,
            tree,
        )
        response.status_code = exc.status_code
        return response

    except (PermissionError, ValueError) as exc:
        for uploaded in uploaded_files:
            try:
                await files.archive(
                    file_id=uploaded.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки "
                    "завершения осмотра: file_id=%s",
                    uploaded.id,
                )

        request.state.inspection_error_message = str(exc)
        request.state.inspection_form_values = {
            "inspection_date": inspection_date.isoformat(),
            "remarks": remarks,
        }
        response = await inspection_task_detail(
            request,
            task_id,
            current_user,
            objects,
            repository,
            service,
            tree,
        )
        response.status_code = (
            status.HTTP_403_FORBIDDEN
            if isinstance(exc, PermissionError)
            else status.HTTP_400_BAD_REQUEST
        )
        return response

    except Exception:
        for uploaded in uploaded_files:
            try:
                await files.archive(
                    file_id=uploaded.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после "
                    "неожиданной ошибки: file_id=%s",
                    uploaded.id,
                )
        raise

    return await _done(request, task.substation_id, task.id)


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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id, task.id)


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
    if current_user.role is not UserRole.MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Проверять результат осмотра может только MANAGER.",
        )
    try:
        await service.review(task_id, actor_id=current_user.id, approve=approve, reason=reason or None)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _done(request, task.substation_id, task.id)
