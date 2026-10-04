from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.objects.exceptions import ObjectAccessDeniedError, ObjectNotFoundError
from app.application.objects.service import ObjectService
from app.application.urza_instructions.service import URZAInstructionService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_urza_instruction_service,
)

router = APIRouter(prefix="/objects", tags=["urza-instructions"])
templates = Jinja2Templates(directory="app/presentation/templates")


async def _ensure_access(object_service: ObjectService, user: User, urza_id: UUID) -> None:
    try:
        await object_service.get_object(user_id=user.id, object_type="urza", object_id=urza_id)
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="URZA не найдено") from exc


async def _render_instruction(request: Request, urza_id: UUID, user: User,
                              service: URZAInstructionService, instruction_version: UUID | None = None,
                              history_open: bool = False):
    instruction = await service.get_by_urza(user.id, urza_id)
    versions = await service.get_versions(user.id, urza_id) if instruction else []
    current_version = await service.get_current_version(user.id, urza_id) if instruction else None
    selected_version = None
    if instruction_version is not None:
        selected_version = await service.get_version_by_id(user.id, instruction_version)
    if selected_version is None:
        selected_version = versions[0] if versions else current_version
    actions = await service.get_available_actions(user.id, selected_version) if selected_version else set()
    return templates.TemplateResponse(request=request, name="objects/urza_instruction.html", context={
        "urza_id": urza_id, "instruction": instruction, "versions": versions,
        "current_version": current_version, "selected_version": selected_version,
        "actions": actions, "history_open": history_open, "current_user": user,
        "can_create": user.role.value in {"engineer", "admin", "superadmin", "manager"},
    })


@router.get("/urza/{urza_id}/instruction")
async def get_urza_instruction(
    request: Request, urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)],
    instruction_version: UUID | None = Query(default=None),
):
    await _ensure_access(object_service, current_user, urza_id)
    return await _render_instruction(request, urza_id, current_user, service, instruction_version,
                                     history_open=instruction_version is not None)


@router.get("/urza/{urza_id}/instruction/new")
async def get_new_instruction_form(request: Request, urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],):
    await _ensure_access(object_service, current_user, urza_id)
    return templates.TemplateResponse(request=request, name="objects/urza_instruction_form.html",
                                      context={"urza_id": urza_id, "new_version": False})


@router.get("/urza/{urza_id}/instruction/new-version")
async def get_new_instruction_version_form(request: Request, urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)],):
    await _ensure_access(object_service, current_user, urza_id)
    instruction = await service.get_by_urza(current_user.id, urza_id)
    if instruction is None:
        raise HTTPException(status_code=404, detail="Инструкция РЗА не найдена.")
    return templates.TemplateResponse(request=request, name="objects/urza_instruction_form.html",
        context={"urza_id": urza_id, "instruction_id": instruction.id, "new_version": True})


async def _upload(file_service: FileService, user_id: UUID, upload: UploadFile, label: str):
    content = await upload.read()
    filename = upload.filename or label
    return await file_service.upload(actor_id=user_id, content=content, original_name=filename,
        display_name=filename, extension=("." + filename.rsplit(".", 1)[1] if "." in filename else ""),
        mime_type=upload.content_type or "application/octet-stream")


@router.post("/urza/{urza_id}/instruction")
async def create_instruction(request: Request, urza_id: UUID,
    effective_date: Annotated[date, Form()], scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    editable_file: Annotated[UploadFile | None, FastAPIFile()] = None):
    await _ensure_access(object_service, current_user, urza_id)
    scan = await _upload(file_service, current_user.id, scan_file, "scan")
    editable = await _upload(file_service, current_user.id, editable_file, "editable") if editable_file and editable_file.filename else None
    try:
        await service.create(user_id=current_user.id, urza_id=urza_id, effective_date=effective_date,
            scan_file_id=scan.id, editable_file_id=editable.id if editable else None,
            change_description=change_description, change_justification=change_justification)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _render_instruction(request, urza_id, current_user, service)


@router.post("/urza/{urza_id}/instruction/{instruction_id}/versions")
async def create_instruction_version(request: Request, urza_id: UUID, instruction_id: UUID,
    effective_date: Annotated[date, Form()], scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    editable_file: Annotated[UploadFile | None, FastAPIFile()] = None):
    await _ensure_access(object_service, current_user, urza_id)
    scan = await _upload(file_service, current_user.id, scan_file, "scan")
    editable = await _upload(file_service, current_user.id, editable_file, "editable") if editable_file and editable_file.filename else None
    try:
        created = await service.create_version(user_id=current_user.id, instruction_id=instruction_id,
            effective_date=effective_date, scan_file_id=scan.id, editable_file_id=editable.id if editable else None,
            change_description=change_description, change_justification=change_justification)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _render_instruction(request, urza_id, current_user, service, created.id, True)


async def _transition(request: Request, urza_id: UUID, version_id: UUID, current_user: User,
                      service: URZAInstructionService, operation: str):
    try:
        await getattr(service, operation)(current_user.id, version_id, urza_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _render_instruction(request, urza_id, current_user, service, version_id, True)


@router.post("/urza/{urza_id}/instruction/versions/{version_id}/submit")
async def submit_instruction(request: Request, urza_id: UUID, version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)]):
    return await _transition(request, urza_id, version_id, current_user, service, "submit_for_review")


@router.post("/urza/{urza_id}/instruction/versions/{version_id}/approve")
async def approve_instruction(request: Request, urza_id: UUID, version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)]):
    return await _transition(request, urza_id, version_id, current_user, service, "approve")


@router.post("/urza/{urza_id}/instruction/versions/{version_id}/return")
async def return_instruction(request: Request, urza_id: UUID, version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[URZAInstructionService, Depends(get_urza_instruction_service)]):
    return await _transition(request, urza_id, version_id, current_user, service, "return_to_draft")
