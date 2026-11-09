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
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.document_templates.service import (
    DocumentFormType,
    DocumentTemplateError,
    DocumentTemplateService,
)
from app.application.files.service import FileService
from app.application.files.validation import FileUploadValidationError
from app.application.maintenance.service import TORecordService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.domain.enums import MaintenanceType, UserRole
from app.domain.file import File
from app.domain.user import User
from app.presentation.auth.dependencies import (
    get_current_user,
    require_non_specialist,
)
from app.presentation.dependencies.services import (
    get_document_form_service,
    get_file_service,
    get_maintenance_service,
    get_object_service,
    get_task_service,
    get_tree_service,
)
from app.presentation.file_uploads import read_upload_content
from app.presentation.responses import TemporaryFileResponse
"""Маршруты просмотра, создания, изменения и согласования записей технического обслуживания."""

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
from app.application.document_templates.service import (
    DocumentTemplateService,
    DocumentFormType,
    DocumentTemplateError,
)
from app.domain.file import File
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
    get_document_form_service,
    get_file_service,
    get_maintenance_service,
    get_object_service,
    get_task_service,
    get_tree_service,
)
from app.presentation.file_uploads import read_upload_content
from app.presentation.responses import TemporaryFileResponse
from app.application.files.validation import FileUploadValidationError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/objects",
    tags=["maintenance"],
)

templates = Jinja2Templates(directory="app/presentation/templates")


@router.get("/urza/{urza_id}/maintenance/form")
async def get_maintenance_form(
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    form_service: Annotated[DocumentTemplateService, Depends(get_document_form_service)],
    archived: bool = Query(default=False),
):
    """Возвращает форму создания или редактирования записи технического обслуживания.
    """
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
            include_archived=archived,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc

    record = await maintenance_service.get_current_approved(current_user.id, urza_id)
    if record is not None and record.signed_form_file_id:
        return RedirectResponse(
            f"/files/{record.signed_form_file_id}/download", status_code=303
        )
    hierarchy = await form_service.get_urza_hierarchy(
        current_user.id, urza_id, archive_only=archived
    )
    try:
        document_path = form_service.create_document(
            DocumentFormType.MAINTENANCE, hierarchy
        )
    except DocumentTemplateError as exc:
        logger.exception("Could not create maintenance DOCX for URZA %s", urza_id)
        raise HTTPException(status_code=500, detail="Не удалось сформировать DOCX-формуляр.") from exc
    return TemporaryFileResponse(
        document_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=form_service.download_filename(DocumentFormType.MAINTENANCE, hierarchy),
    )


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


async def _discard_uploaded_files(
    file_service: FileService,
    uploaded_files: list[File],
) -> None:
    for file in uploaded_files:
        try:
            await file_service.discard_upload(file)
        except Exception:
            logger.exception(
                "Failed to discard uploaded maintenance file %s",
                file.id,
            )


async def _upload_form_file(
    file_service: FileService,
    actor_id: UUID,
    upload: UploadFile | None,
) -> File | None:
    if upload is None or not upload.filename:
        return None
    content = await read_upload_content(upload)
    extension = (
        "." + upload.filename.rsplit(".", 1)[1]
        if "." in upload.filename
        else ""
    )
    return await file_service.upload(
        actor_id=actor_id,
        content=content,
        original_name=upload.filename,
        display_name=upload.filename,
        extension=extension,
        mime_type=upload.content_type or "application/octet-stream",
    )


async def _render_maintenance_list(
    *,
    request: Request,
    urza_id: UUID,
    current_user: User,
    maintenance_service: TORecordService,
    task_service: TaskService,
    tree_service: TreeService,
    error_message: str | None = None,
    status_code: int = status.HTTP_200_OK,
    archived: bool = False,
):
    records = await maintenance_service.get_by_urza(current_user.id, urza_id)
    actions = {
        record.id: await maintenance_service.get_available_actions(
            current_user.id,
            record,
        )
        for record in records
    }
    can_issue_task = False if archived else await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )
    return await _render_maintenance_template(
        request=request,
        template_name="objects/urza_maintenance.html",
        context={
            "current_user": current_user,
            "maintenance_records": records,
            "maintenance_actions": actions,
            "can_issue_task": can_issue_task,
            "can_create_maintenance": (
                not archived and current_user.role is not UserRole.SPECIALIST
            ),
            "is_archived": archived,
            "urza_id": urza_id,
            "error_message": error_message,
        },
        current_user=current_user,
        tree_service=tree_service,
        status_code=status_code,
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
    """Отображает список записей ТО выбранного УРЗА.
    """
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

    return await _render_maintenance_list(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
        archived=archived,
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
    """Отображает форму создания записи ТО для устройства.
    """
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


@router.get(
    "/urza/{urza_id}/maintenance/{record_id}/edit",
    dependencies=[Depends(require_non_specialist)],
)
async def get_edit_urza_maintenance_form(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    """Отображает форму редактирования черновика записи ТО.
    """
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
        record = await maintenance_service.get_by_id(
            current_user.id,
            record_id,
            urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Запись ТО не найдена.")
    if "edit" not in await maintenance_service.get_available_actions(
        current_user.id,
        record,
    ):
        raise HTTPException(status_code=403, detail="Редактирование записи ТО запрещено.")
    form_values = {
        "maintenance_date": record.maintenance_date.isoformat(),
        "maintenance_type": record.maintenance_type.value,
        "historical_data": record.historical_data,
        "detected_deviations": record.detected_deviations,
        "measures_taken": record.measures_taken,
    }
    return await _render_maintenance_template(
        request=request,
        template_name="objects/urza_maintenance_form.html",
        context={
            "urza_id": urza_id,
            "maintenance_types": list(MaintenanceType),
            "form_values": form_values,
            "task_id": record.task_id,
            "record": record,
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
    """Создаёт запись технического обслуживания и сохраняет загруженные файлы.
    """
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

    uploaded_files: list[File] = []

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
        uploaded_files.append(saved_signed_form)

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
            uploaded_files.append(saved_scan)

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
            uploaded_files.append(saved_editable)

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
        await _discard_uploaded_files(
            file_service,
            uploaded_files,
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

    except FileUploadValidationError as exc:
        await _discard_uploaded_files(
            file_service,
            uploaded_files,
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
            status_code=exc.status_code,
        )

    except ValueError as exc:
        await _discard_uploaded_files(
            file_service,
            uploaded_files,
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
        await _discard_uploaded_files(
            file_service,
            uploaded_files,
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

    return await _render_maintenance_list(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
    )


@router.post(
    "/urza/{urza_id}/maintenance/{record_id}/edit",
    dependencies=[Depends(require_non_specialist)],
)
async def update_urza_maintenance(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    maintenance_date: Annotated[date, Form()],
    maintenance_type: Annotated[MaintenanceType, Form()],
    detected_deviations: Annotated[str, Form()],
    measures_taken: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    historical_data: Annotated[bool, Form()] = False,
    signed_form_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    scan_protocol_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    editable_protocol_file: Annotated[UploadFile | None, FastAPIFile()] = None,
):
    """Обновляет черновик записи технического обслуживания.
    """
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
        record = await maintenance_service.get_by_id(
            current_user.id,
            record_id,
            urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Запись ТО не найдена.")

    form_values = {
        "maintenance_date": maintenance_date.isoformat(),
        "maintenance_type": maintenance_type.value,
        "historical_data": historical_data,
        "detected_deviations": detected_deviations,
        "measures_taken": measures_taken,
    }
    original_file_ids = {
        record.signed_form_file_id,
        record.scan_protocol_id,
        record.editable_protocol_id,
    }
    uploaded_files: list[File] = []
    try:
        new_signed = await _upload_form_file(
            file_service, current_user.id, signed_form_file
        )
        if new_signed is not None:
            uploaded_files.append(new_signed)
        new_scan = await _upload_form_file(
            file_service, current_user.id, scan_protocol_file
        )
        if new_scan is not None:
            uploaded_files.append(new_scan)
        new_editable = await _upload_form_file(
            file_service, current_user.id, editable_protocol_file
        )
        if new_editable is not None:
            uploaded_files.append(new_editable)
        updated_record = await maintenance_service.update(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
            maintenance_date=maintenance_date,
            maintenance_type=maintenance_type,
            signed_form_file_id=new_signed.id if new_signed else None,
            scan_protocol_id=new_scan.id if new_scan else None,
            editable_protocol_id=new_editable.id if new_editable else None,
            detected_deviations=detected_deviations,
            measures_taken=measures_taken,
            historical_data=historical_data,
        )
    except PermissionError as exc:
        await _discard_uploaded_files(file_service, uploaded_files)
        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "record": record,
                "error_message": str(exc),
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=403,
        )
    except FileUploadValidationError as exc:
        await _discard_uploaded_files(file_service, uploaded_files)
        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "record": record,
                "error_message": str(exc),
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=exc.status_code,
        )
    except ValueError as exc:
        await _discard_uploaded_files(file_service, uploaded_files)
        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "record": record,
                "error_message": str(exc),
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=400,
        )
    except Exception:
        await _discard_uploaded_files(file_service, uploaded_files)
        logger.exception("Failed to update maintenance record %s", record_id)
        return await _render_maintenance_template(
            request=request,
            template_name="objects/urza_maintenance_form.html",
            context={
                "urza_id": urza_id,
                "maintenance_types": list(MaintenanceType),
                "form_values": form_values,
                "record": record,
                "error_message": "Не удалось сохранить изменения записи ТО.",
            },
            current_user=current_user,
            tree_service=tree_service,
            status_code=500,
        )

    current_ids = {
        updated_record.signed_form_file_id,
        updated_record.scan_protocol_id,
        updated_record.editable_protocol_id,
    }
    for file_id in original_file_ids - current_ids:
        try:
            await file_service.archive(file_id=file_id, user_id=current_user.id)
        except Exception:
            logger.exception("Failed to archive replaced maintenance file %s", file_id)

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url=f"/objects/urza/{urza_id}/maintenance",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return await _render_maintenance_list(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
    )


async def _run_maintenance_transition(
    *,
    request: Request,
    urza_id: UUID,
    current_user: User,
    object_service: ObjectService,
    maintenance_service: TORecordService,
    task_service: TaskService,
    tree_service: TreeService,
    record_id: UUID,
    action: str,
    comment: str | None = None,
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc

    try:
        if action == "submit":
            await maintenance_service.submit_for_review(
                current_user.id, record_id, urza_id
            )
        elif action == "approve":
            await maintenance_service.approve(
                current_user.id, record_id, urza_id
            )
        else:
            await maintenance_service.return_to_draft(
                current_user.id, record_id, urza_id, comment or ""
            )
    except PermissionError as exc:
        return await _render_maintenance_list(
            request=request,
            urza_id=urza_id,
            current_user=current_user,
            maintenance_service=maintenance_service,
            task_service=task_service,
            tree_service=tree_service,
            error_message=str(exc),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except ValueError as exc:
        return await _render_maintenance_list(
            request=request,
            urza_id=urza_id,
            current_user=current_user,
            maintenance_service=maintenance_service,
            task_service=task_service,
            tree_service=tree_service,
            error_message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.exception("Failed to %s maintenance record %s", action, record_id)
        return await _render_maintenance_list(
            request=request,
            urza_id=urza_id,
            current_user=current_user,
            maintenance_service=maintenance_service,
            task_service=task_service,
            tree_service=tree_service,
            error_message="Не удалось выполнить действие с записью ТО.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return await _render_maintenance_list(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
    )


@router.post("/urza/{urza_id}/maintenance/{record_id}/submit")
async def submit_maintenance_for_review(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    """Отправляет запись ТО на согласование.
    """
    return await _run_maintenance_transition(
        request=request,
        urza_id=urza_id,
        record_id=record_id,
        current_user=current_user,
        object_service=object_service,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
        action="submit",
    )


@router.post("/urza/{urza_id}/maintenance/{record_id}/approve")
async def approve_maintenance(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    """Утверждает запись ТО от имени руководителя.
    """
    return await _run_maintenance_transition(
        request=request,
        urza_id=urza_id,
        record_id=record_id,
        current_user=current_user,
        object_service=object_service,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
        action="approve",
    )


@router.post("/urza/{urza_id}/maintenance/{record_id}/return")
async def return_maintenance_for_revision(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    comment: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    """Возвращает запись ТО на доработку с комментарием.
    """
    return await _run_maintenance_transition(
        request=request,
        urza_id=urza_id,
        record_id=record_id,
        current_user=current_user,
        object_service=object_service,
        maintenance_service=maintenance_service,
        task_service=task_service,
        tree_service=tree_service,
        action="return",
        comment=comment,
    )
