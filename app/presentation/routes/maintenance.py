import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File as FastAPIFile,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.maintenance.service import TORecordService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.tasks.service import TaskService
from app.domain.enums import MaintenanceType
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_maintenance_service,
    get_object_service,
    get_task_service,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/objects",
    tags=["maintenance"],
)

templates = Jinja2Templates(directory="app/presentation/templates")


async def _archive_uploaded_files(
    file_service: FileService,
    file_ids: list[UUID],
    user_id: UUID,
) -> None:
    for file_id in file_ids:
        try:
            await file_service.archive(
                file_id=file_id,
                user_id=user_id,
            )
        except Exception:
            logger.exception(
                "Failed to archive uploaded maintenance file %s",
                file_id,
            )


@router.get("/urza/{urza_id}/maintenance")
async def get_urza_maintenance(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[
        TORecordService,
        Depends(get_maintenance_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
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

    maintenance_records = await maintenance_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    can_issue_task = await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_maintenance.html",
        context={
            "maintenance_records": maintenance_records,
            "can_issue_task": can_issue_task,
            "urza_id": urza_id,
        },
    )


@router.get("/urza/{urza_id}/maintenance/new")
async def get_new_urza_maintenance_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    task_id: UUID | None = None,
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
        name="objects/urza_maintenance_form.html",
        context={
            "urza_id": urza_id,
            "maintenance_types": list(MaintenanceType),
            "form_values": {},
            "task_id": task_id,
            "error_message": None,
        },
    )


@router.post("/urza/{urza_id}/maintenance")
async def create_urza_maintenance(
    request: Request,
    urza_id: UUID,
    maintenance_date: Annotated[date, Form()],
    maintenance_type: Annotated[MaintenanceType, Form()],
    detected_deviations: Annotated[str, Form()],
    measures_taken: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    maintenance_service: Annotated[
        TORecordService,
        Depends(get_maintenance_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    historical_data: Annotated[bool, Form()] = False,
    signed_form_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
    scan_protocol_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
    editable_protocol_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
    task_id: Annotated[UUID | None, Form()] = None,
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

    form_values = {
        "maintenance_date": maintenance_date.isoformat(),
        "maintenance_type": maintenance_type.value,
        "historical_data": historical_data,
        "detected_deviations": detected_deviations,
        "measures_taken": measures_taken,
    }

    if signed_form_file is None or not signed_form_file.filename:
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": "Загрузите подписанную форму ТО.",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    uploaded_file_ids: list[UUID] = []

    try:
        signed_content = await signed_form_file.read()

        saved_signed_form = await file_service.upload(
            actor_id=current_user.id,
            content=signed_content,
            original_name=signed_form_file.filename,
            display_name=signed_form_file.filename,
            extension=(
                "."
                + signed_form_file.filename.rsplit(".", 1)[1]
                if "." in signed_form_file.filename
                else ""
            ),
            mime_type=(
                signed_form_file.content_type
                or "application/octet-stream"
            ),
        )
        uploaded_file_ids.append(saved_signed_form.id)

        scan_protocol_file_id: UUID | None = None

        if scan_protocol_file and scan_protocol_file.filename:
            scan_content = await scan_protocol_file.read()

            saved_scan = await file_service.upload(
                actor_id=current_user.id,
                content=scan_content,
                original_name=scan_protocol_file.filename,
                display_name=scan_protocol_file.filename,
                extension=(
                    "."
                    + scan_protocol_file.filename.rsplit(".", 1)[1]
                    if "." in scan_protocol_file.filename
                    else ""
                ),
                mime_type=(
                    scan_protocol_file.content_type
                    or "application/octet-stream"
                ),
            )

            scan_protocol_file_id = saved_scan.id
            uploaded_file_ids.append(saved_scan.id)

        editable_protocol_file_id: UUID | None = None

        if (
            editable_protocol_file
            and editable_protocol_file.filename
        ):
            editable_content = await editable_protocol_file.read()

            saved_editable = await file_service.upload(
                actor_id=current_user.id,
                content=editable_content,
                original_name=editable_protocol_file.filename,
                display_name=editable_protocol_file.filename,
                extension=(
                    "."
                    + editable_protocol_file.filename.rsplit(".", 1)[1]
                    if "." in editable_protocol_file.filename
                    else ""
                ),
                mime_type=(
                    editable_protocol_file.content_type
                    or "application/octet-stream"
                ),
            )

            editable_protocol_file_id = saved_editable.id
            uploaded_file_ids.append(saved_editable.id)

        await maintenance_service.create(
            user_id=current_user.id,
            urza_id=urza_id,
            maintenance_date=maintenance_date,
            maintenance_type=maintenance_type,
            signed_form_file_id=saved_signed_form.id,
            scan_protocol_id=scan_protocol_file_id,
            editable_protocol_id=editable_protocol_file_id,
            detected_deviations=detected_deviations,
            measures_taken=measures_taken,
            historical_data=historical_data,
            task_id=task_id,
        )


    except PermissionError as exc:
        await _archive_uploaded_files(
            file_service,
            uploaded_file_ids,
            current_user.id,
        )

        return templates.TemplateResponse(
            request=request,
            name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": str(exc),
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    except ValueError as exc:
        await _archive_uploaded_files(
            file_service,
            uploaded_file_ids,
            current_user.id,
        )

        return templates.TemplateResponse(
            request=request,
            name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


    except Exception:
        await _archive_uploaded_files(
            file_service,
            uploaded_file_ids,
            current_user.id,
        )
        logger.exception(
            "Failed to create maintenance record for URZA %s",
            urza_id,
        )

        return templates.TemplateResponse(
            request=request,
            name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": (
                    "Не удалось сохранить запись технического обслуживания."
                ),
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    maintenance_records = await maintenance_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    can_issue_task = await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_maintenance.html",
        context={
            "maintenance_records": maintenance_records,
            "can_issue_task": can_issue_task,
            "urza_id": urza_id,
        },
    )