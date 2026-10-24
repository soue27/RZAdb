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
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.rza_instructions.service import RZAInstructionService
from app.application.selectivity_schemes.service import SelectivitySchemeService
from app.application.tasks.repository import TaskRepository
from app.application.tree.service import TreeService
from app.domain.enums import TaskStatus, TaskWorkType, UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_rza_instruction_service,
    get_selectivity_scheme_service,
    get_task_repository,
    get_tree_service,
)
from app.presentation.file_uploads import read_upload_content
from app.application.files.validation import FileUploadValidationError

router = APIRouter(prefix="/objects/substation", tags=["substation documents"])
templates = Jinja2Templates(directory="app/presentation/templates")
logger = logging.getLogger(__name__)


async def _check_access(objects: ObjectService, user: User, substation_id: UUID) -> None:
    try:
        await objects.get_object(
            user_id=user.id, object_type="substation", object_id=substation_id
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc


async def _render_form(
    request: Request,
    *,
    substation_id: UUID,
    kind: str,
    current_user: User,
    tree_service: TreeService,
    new_version: bool = False,
    values: dict | None = None,
    error: str | None = None,
    task_id: UUID | None = None,
    response_status: int = status.HTTP_200_OK,
):
    context = {
        "substation_id": substation_id,
        "document_type": kind,
        "new_version": new_version,
        "values": values or {},
        "error_message": error,
        "task_id": task_id,
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/substation_document_form.html",
            context=context,
            status_code=response_status,
        )
    return templates.TemplateResponse(
        request=request,
        name="objects/substation_document_page.html",
        status_code=response_status,
        context={
            **context,
            "current_user": current_user,
            "tree": await tree_service.get_tree(user_id=current_user.id),
            "page_title": "Документ подстанции",
            "content_template": "objects/substation_document_form.html",

        },
    )


@router.get("/{substation_id}/instructions/new")
async def new_instruction_form(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
    instruction_service: Annotated[RZAInstructionService, Depends(get_rza_instruction_service)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    new_version: bool = False,
    task_id: UUID | None = None,
):
    await _check_access(objects, current_user, substation_id)
    if current_user.role not in {
        UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.MANAGER
    }:
        raise HTTPException(status_code=403, detail="Создание документа запрещено.")
    if task_id is not None:
        task = await tasks.get_active_by_id(task_id)
        if task is None or task.substation_id != substation_id or task.work_type is not TaskWorkType.INSTRUCTION or task.assigned_to != current_user.id or task.status is not TaskStatus.IN_PROGRESS:
            raise HTTPException(status_code=403, detail="Задание недоступно для выполнения.")
        new_version = await instruction_service.get_by_substation(current_user.id, substation_id) is not None
    return await _render_form(
        request, substation_id=substation_id, kind="instruction",
        current_user=current_user, tree_service=tree, new_version=new_version, task_id=task_id,
    )


@router.get("/{substation_id}/selectivity-schemes/new")
async def new_scheme_form(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
    scheme_service: Annotated[SelectivitySchemeService, Depends(get_selectivity_scheme_service)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    new_version: bool = False,
    task_id: UUID | None = None,
):
    await _check_access(objects, current_user, substation_id)
    if current_user.role not in {
        UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.MANAGER
    }:
        raise HTTPException(status_code=403, detail="Создание документа запрещено.")
    if task_id is not None:
        task = await tasks.get_active_by_id(task_id)
        if task is None or task.substation_id != substation_id or task.work_type is not TaskWorkType.SCHEMES or task.assigned_to != current_user.id or task.status is not TaskStatus.IN_PROGRESS:
            raise HTTPException(status_code=403, detail="Задание недоступно для выполнения.")
        new_version = await scheme_service.get_by_substation(current_user.id, substation_id) is not None
    return await _render_form(
        request, substation_id=substation_id, kind="scheme",
        current_user=current_user, tree_service=tree, new_version=new_version, task_id=task_id,
    )


async def _upload(file_service: FileService, user: User, upload: UploadFile):
    filename = upload.filename or "document"
    return await file_service.upload(
        actor_id=user.id,
        content=await read_upload_content(upload),
        original_name=filename,
        display_name=filename,
        extension=("." + filename.rsplit(".", 1)[1]) if "." in filename else "",
        mime_type=upload.content_type or "application/octet-stream",
    )


async def _create_document(
    request: Request,
    substation_id: UUID,
    kind: str,
    effective_date: str,
    scan_file: UploadFile | None,
    editable_file: UploadFile | None,
    number: str | None,
    name: str | None,
    change_description: str | None,
    change_justification: str | None,
    new_version: bool,
    instruction_service: RZAInstructionService,
    scheme_service: SelectivitySchemeService,
    file_service: FileService,
    objects: ObjectService,
    tree: TreeService,
    current_user: User,
    task_repository: TaskRepository,
    task_id: UUID | None,
):
    await _check_access(objects, current_user, substation_id)
    if task_id is not None:
        task = await task_repository.get_active_by_id(task_id)
        expected_type = TaskWorkType.INSTRUCTION if kind == "instruction" else TaskWorkType.SCHEMES
        if task is None or task.substation_id != substation_id or task.work_type is not expected_type or task.assigned_to != current_user.id or task.status is not TaskStatus.IN_PROGRESS:
            raise HTTPException(status_code=403, detail="Задание недоступно для выполнения.")
        existing_result = (
            await task_repository.get_substation_instruction_version_by_task_id(task_id)
            if kind == "instruction"
            else await task_repository.get_selectivity_version_by_task_id(task_id)
        )
        if existing_result is not None:
            raise HTTPException(status_code=400, detail="Для этого задания уже сохранён результат.")
    values = {
        "effective_date": effective_date,
        "number": number or "",
        "name": name or "",
        "change_description": change_description or "",
        "change_justification": change_justification or "",
    }
    try:
        if not effective_date:
            raise ValueError("Укажите дату вступления.")
        parsed_date = date.fromisoformat(effective_date)
        if kind == "scheme" and (
            not number or not number.strip() or len(number) > 255
            or not name or not name.strip() or len(name) > 500
        ):
            raise ValueError("Укажите номер (до 255 символов) и наименование (до 500 символов).")
        if scan_file is None or not scan_file.filename:
            raise ValueError("Приложите скан документа.")

    except (ValueError, TypeError) as exc:
        return await _render_form(
            request, substation_id=substation_id, kind=kind,
            current_user=current_user, tree_service=tree, new_version=new_version,
            values=values, error=str(exc),
            task_id=task_id,
        )


    uploaded = []
    try:
        scan = await _upload(file_service, current_user, scan_file)
        uploaded.append(scan)

        editable = None
        if editable_file and editable_file.filename:
            editable = await _upload(file_service, current_user, editable_file)
            uploaded.append(editable)

        if kind == "instruction":
            if new_version:
                instruction = await instruction_service.get_by_substation(
                    current_user.id, substation_id
                )
                if instruction is None:
                    raise ValueError("Инструкция РЗА не найдена.")

                await instruction_service.create_version(
                    user_id=current_user.id,
                    instruction_id=instruction.id,
                    effective_date=parsed_date,
                    scan_file_id=scan.id,
                    editable_file_id=editable.id if editable else None,
                    change_description=change_description,
                    change_justification=change_justification,
                    task_id=task_id,
                )
            else:
                await instruction_service.create(
                    user_id=current_user.id,
                    substation_id=substation_id,
                    effective_date=parsed_date,
                    scan_file_id=scan.id,
                    editable_file_id=editable.id if editable else None,
                    change_description=change_description,
                    change_justification=change_justification,
                    task_id=task_id,
                )
        elif new_version:
            scheme = await scheme_service.get_by_substation(
                current_user.id, substation_id
            )
            if scheme is None:
                raise ValueError("Схема селективности не найдена.")

            await scheme_service.create_version(
                user_id=current_user.id,
                scheme_id=scheme.id,
                number=number or "",
                name=name or "",
                effective_date=parsed_date,
                scan_file_id=scan.id,
                editable_file_id=editable.id if editable else None,
                change_description=change_description,
                change_justification=change_justification,
                task_id=task_id,
            )
        else:
            await scheme_service.create(
                user_id=current_user.id,
                substation_id=substation_id,
                number=number or "",
                name=name or "",
                effective_date=parsed_date,
                scan_file_id=scan.id,
                editable_file_id=editable.id if editable else None,
                change_description=change_description,
                change_justification=change_justification,
                task_id=task_id,
            )

    except FileUploadValidationError as exc:
        for uploaded_file in uploaded:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки "
                    "валидации документа подстанции: file_id=%s",
                    uploaded_file.id,
                )

        return await _render_form(
            request,
            substation_id=substation_id,
            kind=kind,
            current_user=current_user,
            tree_service=tree,
            new_version=new_version,
            values=values,
            error=str(exc),
            task_id=task_id,
            response_status=exc.status_code,
        )

    except (ValueError, PermissionError) as exc:
        for uploaded_file in uploaded:
            await file_service.archive(
                file_id=uploaded_file.id,
                user_id=current_user.id,
            )

        return await _render_form(
            request,
            substation_id=substation_id,
            kind=kind,
            current_user=current_user,
            tree_service=tree,
            new_version=new_version,
            values=values,
            error=str(exc),
            task_id=task_id,
        )


    except Exception:
        for uploaded_file in uploaded:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки создания документа: "
                    "file_id=%s",
                    uploaded_file.id,
                )
        raise

    destination = (
        f"/tasks/{task_id}" if task_id is not None else
        f"/objects/substation/{substation_id}?tab="
        f"{'instructions' if kind == 'instruction' else 'selectivity-schemes'}"
    )
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": destination})
    return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)




@router.post("/{substation_id}/instructions")
async def create_instruction(
    request: Request, substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    instruction_service: Annotated[RZAInstructionService, Depends(get_rza_instruction_service)],
    scheme_service: Annotated[SelectivitySchemeService, Depends(get_selectivity_scheme_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    effective_date: Annotated[str, Form()] = "",
    scan_file: Annotated[UploadFile | None, File()] = None,
    editable_file: Annotated[UploadFile | None, File()] = None,
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    new_version: Annotated[bool, Form()] = False,
    task_id: Annotated[UUID | None, Form()] = None,
):
    return await _create_document(
        request, substation_id, "instruction", effective_date, scan_file,
        editable_file, None, None, change_description, change_justification,
        new_version, instruction_service, scheme_service, file_service,
        objects, tree, current_user, tasks, task_id,
    )


@router.post("/{substation_id}/selectivity-schemes")
async def create_selectivity_scheme(
    request: Request, substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    instruction_service: Annotated[RZAInstructionService, Depends(get_rza_instruction_service)],
    scheme_service: Annotated[SelectivitySchemeService, Depends(get_selectivity_scheme_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    objects: Annotated[ObjectService, Depends(get_object_service)],
    tree: Annotated[TreeService, Depends(get_tree_service)],
    tasks: Annotated[TaskRepository, Depends(get_task_repository)],
    effective_date: Annotated[str, Form()] = "",
    number: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    scan_file: Annotated[UploadFile | None, File()] = None,
    editable_file: Annotated[UploadFile | None, File()] = None,
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    new_version: Annotated[bool, Form()] = False,
    task_id: Annotated[UUID | None, Form()] = None,
):
    return await _create_document(
        request, substation_id, "scheme", effective_date, scan_file,
        editable_file, number, name, change_description, change_justification,
        new_version, instruction_service, scheme_service, file_service,
        objects, tree, current_user, tasks, task_id,
    )


@router.post("/{substation_id}/instructions/versions/{version_id}/{action}")
async def instruction_transition(
    request: Request, substation_id: UUID, version_id: UUID, action: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[RZAInstructionService, Depends(get_rza_instruction_service)],
):
    return await _transition(request, substation_id, version_id, action, current_user, service)


@router.post("/{substation_id}/selectivity-schemes/versions/{version_id}/{action}")
async def scheme_transition(
    request: Request, substation_id: UUID, version_id: UUID, action: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SelectivitySchemeService, Depends(get_selectivity_scheme_service)],
):
    return await _transition(request, substation_id, version_id, action, current_user, service)


async def _transition(request, substation_id, version_id, action, user, service):
    if action not in {"submit", "approve", "return"}:
        raise HTTPException(status_code=404, detail="Действие не найдено.")
    try:
        if action == "submit":
            await service.submit_for_review(user.id, substation_id, version_id)
        else:
            await service.review(user.id, substation_id, version_id, approve=action == "approve")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tab = "instructions" if isinstance(service, RZAInstructionService) else "selectivity-schemes"
    destination = f"/objects/substation/{substation_id}?tab={tab}"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": destination})
    return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
