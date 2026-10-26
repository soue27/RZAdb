from datetime import date
from typing import Annotated
from uuid import UUID
import logging

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi import (
    File as FastAPIFile,
)
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.tasks.service import TaskService
from app.application.urza_instructions.service import URZAInstructionService
from app.domain.enums import UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_task_service,
    get_urza_instruction_service,
)
from app.presentation.file_uploads import read_upload_content
from app.application.files.validation import FileUploadValidationError


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/objects",
    tags=["urza-instructions"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)


async def _ensure_access(
    object_service: ObjectService,
    user: User,
    urza_id: UUID,
    *,
    include_archived: bool = False,
) -> None:
    try:
        await object_service.get_object(
            user_id=user.id,
            object_type="urza",
            object_id=urza_id,
            include_archived=include_archived,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=403,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="URZA не найдено",
        ) from exc


async def _render_instruction(
    request: Request,
    urza_id: UUID,
    user: User,
    service: URZAInstructionService,
    task_service: TaskService,
    instruction_version: UUID | None = None,
    history_open: bool = False,
    is_archived: bool = False,
):
    instruction = await service.get_by_urza(
        user.id,
        urza_id,
    )

    versions = (
        await service.get_versions(user.id, urza_id)
        if instruction
        else []
    )
    working_versions = (
        await service.get_working_versions(user.id, urza_id)
        if instruction
        else []
    )

    current_version = (
        await service.get_current_version(user.id, urza_id)
        if instruction
        else None
    )

    selected_version = None

    if instruction_version is not None:
        selected_version = await service.get_version_by_id(
            user.id,
            instruction_version,
        )
        # A user may have access to several URZA objects. History selection
        # must still remain within the instruction currently being rendered.
        if (
            selected_version is not None
            and instruction is not None
            and selected_version.urza_instruction_id != instruction.id
        ):
            selected_version = None

    if selected_version is None:
        selected_version = (
            working_versions[0]
            if working_versions
            else current_version
        )

    actions = (
        await service.get_available_actions(
            user.id,
            selected_version,
        )
        if selected_version and not is_archived
        else set()
    )

    can_issue_task = False if is_archived else await task_service.can_issue_task(
        actor_id=user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_instruction.html",
        context={
            "urza_id": urza_id,
            "instruction": instruction,
            "versions": versions,
            "working_versions": working_versions,
            "current_version": current_version,
            "selected_version": selected_version,
            "actions": actions,
            "history_open": history_open,
            "is_archived": is_archived,
            "current_user": user,
            "can_create": not is_archived and user.role.value
            in {
                "engineer",
                "admin",
                "superadmin",
                "manager",
            },
            "can_issue_task": can_issue_task,
        },
    )


@router.get("/urza/{urza_id}/instruction")
async def get_urza_instruction(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    instruction_version: UUID | None = Query(default=None),
    archived: bool = Query(default=False),
):
    await _ensure_access(
        object_service,
        current_user,
        urza_id,
        include_archived=archived,
    )

    return await _render_instruction(
        request,
        urza_id,
        current_user,
        service,
        task_service,
        instruction_version,
        history_open=instruction_version is not None,
        is_archived=archived,
    )


@router.get("/urza/{urza_id}/instruction/new")
async def get_new_instruction_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
):
    await _ensure_access(
        object_service,
        current_user,
        urza_id,
    )

    if current_user.role not in {
        UserRole.MANAGER,
        UserRole.ENGINEER,
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    }:
        raise HTTPException(
            status_code=403,
            detail="Создавать инструкцию с текущей ролью запрещено.",
        )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_instruction_form.html",
        context={
            "urza_id": urza_id,
            "new_version": False,
        },
    )


@router.get("/urza/{urza_id}/instruction/new-version")
async def get_new_instruction_version_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
):
    await _ensure_access(
        object_service,
        current_user,
        urza_id,
    )

    instruction = await service.get_by_urza(
        current_user.id,
        urza_id,
    )

    if instruction is None:
        raise HTTPException(
            status_code=404,
            detail="Инструкция РЗА не найдена.",
        )

    versions = await service.get_versions(current_user.id, urza_id)
    actions = (
        await service.get_available_actions(current_user.id, versions[0])
        if versions
        else set()
    )
    if "new_version" not in actions:
        raise HTTPException(
            status_code=403,
            detail="Создание новой версии инструкции запрещено.",
        )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_instruction_form.html",
        context={
            "urza_id": urza_id,
            "instruction_id": instruction.id,
            "new_version": True,
        },
    )


async def _upload(
    file_service: FileService,
    user_id: UUID,
    upload: UploadFile,
    label: str,
):
    content = await read_upload_content(upload)
    filename = upload.filename or label

    return await file_service.upload(
        actor_id=user_id,
        content=content,
        original_name=filename,
        display_name=filename,
        extension=(
            "."
            + filename.rsplit(".", 1)[1]
            if "." in filename
            else ""
        ),
        mime_type=upload.content_type or "application/octet-stream",
    )


@router.post("/urza/{urza_id}/instruction")
async def create_instruction(
    request: Request,
    urza_id: UUID,
    effective_date: Annotated[date, Form()],
    scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
):
    await _ensure_access(
        object_service,
        current_user,
        urza_id,
    )

    uploaded_files = []

    try:
        scan = await _upload(
            file_service,
            current_user.id,
            scan_file,
            "scan",
        )
        uploaded_files.append(scan)

        editable = (
            await _upload(
                file_service,
                current_user.id,
                editable_file,
                "editable",
            )
            if editable_file and editable_file.filename
            else None
        )

        if editable is not None:
            uploaded_files.append(editable)

        await service.create(
            user_id=current_user.id,
            urza_id=urza_id,
            effective_date=effective_date,
            scan_file_id=scan.id,
            editable_file_id=editable.id if editable else None,
            change_description=change_description,
            change_justification=change_justification,
        )


    except FileUploadValidationError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки "
                    "валидации инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки доступа "
                    "при создании инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки данных "
                    "при создании инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после неожиданной "
                    "ошибки при обработке инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise

    return await _render_instruction(
        request,
        urza_id,
        current_user,
        service,
        task_service,
    )


@router.post("/urza/{urza_id}/instruction/{instruction_id}/versions")
async def create_instruction_version(
    request: Request,
    urza_id: UUID,
    instruction_id: UUID,
    effective_date: Annotated[date, Form()],
    scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    change_description: Annotated[str | None, Form()] = None,
    change_justification: Annotated[str | None, Form()] = None,
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
):
    await _ensure_access(
        object_service,
        current_user,
        urza_id,
    )

    uploaded_files = []

    try:
        scan = await _upload(
            file_service,
            current_user.id,
            scan_file,
            "scan",
        )
        uploaded_files.append(scan)

        editable = (
            await _upload(
                file_service,
                current_user.id,
                editable_file,
                "editable",
            )
            if editable_file and editable_file.filename
            else None
        )

        if editable is not None:
            uploaded_files.append(editable)

        created = await service.create_version(
            user_id=current_user.id,
            instruction_id=instruction_id,
            effective_date=effective_date,
            scan_file_id=scan.id,
            editable_file_id=editable.id if editable else None,
            change_description=change_description,
            change_justification=change_justification,
        )

    except FileUploadValidationError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки "
                    "валидации инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки доступа "
                    "при создании версии инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после ошибки данных "
                    "при создании версии инструкции РЗА: file_id=%s",
                    uploaded_file.id,
                )
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception:
        for uploaded_file in uploaded_files:
            try:
                await file_service.archive(
                    file_id=uploaded_file.id,
                    user_id=current_user.id,
                )
            except Exception:
                logger.exception(
                    "Не удалось архивировать файл после неожиданной "
                    "ошибки при создании версии инструкции РЗА: "
                    "file_id=%s",
                    uploaded_file.id,
                )
        raise

    return await _render_instruction(
        request,
        urza_id,
        current_user,
        service,
        task_service,
        created.id,
        True,
    )


async def _transition(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    current_user: User,
    service: URZAInstructionService,
    task_service: TaskService,
    operation: str,
):
    try:
        await getattr(service, operation)(
            current_user.id,
            version_id,
            urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return await _render_instruction(
        request,
        urza_id,
        current_user,
        service,
        task_service,
        version_id,
        True,
    )


@router.post(
    "/urza/{urza_id}/instruction/versions/{version_id}/submit"
)
async def submit_instruction(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
):
    return await _transition(
        request,
        urza_id,
        version_id,
        current_user,
        service,
        task_service,
        "submit_for_review",
    )


@router.post(
    "/urza/{urza_id}/instruction/versions/{version_id}/approve"
)
async def approve_instruction(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
):
    return await _transition(
        request,
        urza_id,
        version_id,
        current_user,
        service,
        task_service,
        "approve",
    )


@router.post(
    "/urza/{urza_id}/instruction/versions/{version_id}/return"
)
async def return_instruction(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
):
    return await _transition(
        request,
        urza_id,
        version_id,
        current_user,
        service,
        task_service,
        "return_to_draft",
    )
