from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Form, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi import File as FastAPIFile

from app.application.files.service import FileService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.programs.service import ProgramService
from app.domain.enums import ProgramType
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_program_service,
)

router = APIRouter(
    prefix="/objects",
    tags=["objects"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)


async def _render_urza_programs(
    request: Request,
    urza_id: UUID,
    current_user: User,
    program_service: ProgramService,
):
    programs = await program_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    program_actions = {
        program.id: await program_service.get_available_actions(
            user_id=current_user.id,
            program=program,
        )
        for program in programs
    }

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs.html",
        context={
            "urza_id": urza_id,
            "programs": programs,
            "program_actions": program_actions,
        },
    )


@router.get("/urza/{urza_id}/programs")
async def get_urza_programs(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
    )


@router.get("/urza/{urza_id}/programs/new")
async def get_new_urza_program_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_program_form.html",
        context={
            "urza_id": urza_id,
            "program_types": list(ProgramType),
        },
    )


@router.post("/urza/{urza_id}/programs")
async def create_urza_program(
    request: Request,
    urza_id: UUID,
    program_type: Annotated[ProgramType, Form()],
    program_number: Annotated[str, Form()],
    scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    scan_content = await scan_file.read()

    saved_scan = await file_service.upload(
        actor_id=current_user.id,
        content=scan_content,
        original_name=scan_file.filename or "scan",
        display_name=scan_file.filename or "Скан программы",
        extension=(
            "." + scan_file.filename.rsplit(".", 1)[1]
            if scan_file.filename and "." in scan_file.filename
            else ""
        ),
        mime_type=scan_file.content_type or "application/octet-stream",
    )

    editable_file_id = None

    if editable_file and editable_file.filename:
        editable_content = await editable_file.read()

        saved_editable = await file_service.upload(
            actor_id=current_user.id,
            content=editable_content,
            original_name=editable_file.filename,
            display_name=editable_file.filename,
            extension=(
                "." + editable_file.filename.rsplit(".", 1)[1]
                if "." in editable_file.filename
                else ""
            ),
            mime_type=editable_file.content_type or "application/octet-stream",
        )

        editable_file_id = saved_editable.id

    await program_service.create(
        user_id=current_user.id,
        urza_id=urza_id,
        program_type=program_type,
        program_number=program_number,
        scan_file_id=saved_scan.id,
        editable_file_id=editable_file_id,
    )

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
    )


@router.post("/urza/{urza_id}/programs/{program_id}/submit")
async def submit_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
):
    try:
        await program_service.submit_for_review(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
    )


@router.post("/urza/{urza_id}/programs/{program_id}/approve")
async def approve_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
):
    try:
        await program_service.approve(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
    )


@router.post("/urza/{urza_id}/programs/{program_id}/return")
async def return_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
):
    try:
        await program_service.return_to_draft(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
    )