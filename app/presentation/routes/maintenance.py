import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi import (
    File as FastAPIFile,
)
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.maintenance.service import TORecordService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.domain.enums import MaintenanceType, UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import (
    get_current_user,
    require_non_specialist,
)
from app.presentation.dependencies.services import (
    get_file_service,
    get_maintenance_service,
    get_object_service,
    get_task_service,
    get_tree_service,
)
from app.presentation.file_uploads import read_upload_content

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/objects",
    tags=["maintenance"],
)

templates = Jinja2Templates(directory="app/presentation/templates")


async def _render_maintenance_template(
    *,
    request: Request,
    template_name: str,
    context: dict,
    current_user: User,
    tree_service: TreeService,
    status_code: int = status.HTTP_200_OK,
):
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context=context,
            status_code=(
                status.HTTP_200_OK
                if status_code >= status.HTTP_400_BAD_REQUEST
                else status_code
            ),
        )

    tree = await tree_service.get_tree(user_id=current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_maintenance_page.html",
        context={
            **context,
            "current_user": current_user,
            "tree": tree,
            "content_template": template_name,
        },
        status_code=status_code,
    )


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
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    archived: bool = Query(default=False),
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
            include_archived=archived,
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

    can_issue_task = False if archived else await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    return await _render_maintenance_template(
        request=request,
        template_name="objects/urza_maintenance.html",
        context={
            "maintenance_records": maintenance_records,
            "can_issue_task": can_issue_task,
            "can_create_maintenance": (
                not archived and current_user.role is not UserRole.SPECIALIST
            ),
            "is_archived": archived,
            "urza_id": urza_id,
        },
        current_user=current_user,
        tree_service=tree_service,
    )


@router.get(
    "/urza/{urza_id}/maintenance/new",
    dependencies=[Depends(require_non_specialist)],
)
async def get_new_urza_maintenance_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    maintenance_service: Annotated[
        TORecordService,
        Depends(get_maintenance_service),
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

    if task_id is not None:
        try:
            await maintenance_service.validate_task_for_result(
                current_user.id,
                urza_id,
                task_id,
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

    return await _render_maintenance_template(
        request=request,
        template_name="objects/urza_maintenance_form.html",
        context={
            "urza_id": urza_id,
            "maintenance_types": list(MaintenanceType),
            "form_values": {},
            "task_id": task_id,
            "error_message": None,
        },
        current_user=current_user,
        tree_service=tree_service,
    )


@router.post(
    "/urza/{urza_id}/maintenance",
    dependencies=[Depends(require_non_specialist)],
)
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
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
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
        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": "Загрузите подписанную форму ТО.",
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    uploaded_file_ids: list[UUID] = []

    try:
        signed_content = await read_upload_content(signed_form_file)

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
            scan_content = await read_upload_content(scan_protocol_file)

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
            editable_content = await read_upload_content(editable_protocol_file)

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

        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": str(exc),
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    except ValueError as exc:
        await _archive_uploaded_files(
            file_service,
            uploaded_file_ids,
            current_user.id,
        )

        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": str(exc),
            },
            current_user=current_user,
            tree_service=tree_service,
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

        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "task_id": task_id,
                "error_message": (
                    "Не удалось сохранить запись технического обслуживания."
                ),
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url=f"/objects/urza/{urza_id}/maintenance",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    maintenance_records = await maintenance_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    can_issue_task = await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    return await _render_maintenance_template(
        request=request,
        template_name="objects/urza_maintenance.html",
        context={
            "maintenance_records": maintenance_records,
            "can_issue_task": can_issue_task,
            "can_create_maintenance": current_user.role is not UserRole.SPECIALIST,
            "urza_id": urza_id,
        },
        current_user=current_user,
        tree_service=tree_service,
    )
