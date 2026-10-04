import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, Form, HTTPException
from fastapi import Request, UploadFile, status
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.schema.service import SchemaService
from app.domain.schema import SchemaRecord
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_schema_service,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/objects", tags=["schemes"])
templates = Jinja2Templates(directory="app/presentation/templates")


async def _check_urza_access(
    object_service: ObjectService,
    user_id: UUID,
    urza_id: UUID,
) -> None:
    try:
        await object_service.get_object(
            user_id=user_id,
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


async def _render_schemes(
    request: Request,
    urza_id: UUID,
    current_user: User,
    schema_service: SchemaService,
    *,
    error_message: str | None = None,
    notice_message: str | None = None,
    response_status: int = status.HTTP_200_OK,
):
    schema_form, schema_records = await schema_service.get_details(
        user_id=current_user.id,
        urza_id=urza_id,
    )
    current_record = await schema_service.get_current(
        user_id=current_user.id,
        urza_id=urza_id,
    )
    schema_actions = {
        record.id: await schema_service.get_available_actions(
            user_id=current_user.id,
            record=record,
        )
        for record in schema_records
    }
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_schemas.html",
        context={
            "schema_form": schema_form,
            "schema_records": schema_records,
            "current_record": current_record,
            "schema_actions": schema_actions,
            "urza_id": urza_id,
            "current_user": current_user,
            "error_message": error_message,
            "notice_message": notice_message,
        },
        status_code=response_status,
    )


async def _render_schema_form(
    request: Request,
    urza_id: UUID,
    *,
    record: SchemaRecord | None = None,
    task_id: UUID | None = None,
    form_values: dict | None = None,
    error_message: str | None = None,
    response_status: int = status.HTTP_200_OK,
):
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_schemas_form.html",
        context={
            "urza_id": urza_id,
            "record": record,
            "task_id": task_id or (record.task_id if record else None),
            "form_values": form_values or {},
            "error_message": error_message,
            "is_edit": record is not None,
        },
        status_code=response_status,
    )


def _upload_extension(filename: str | None) -> str:
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[1]
    return ""


async def _upload_file(
    file_service: FileService,
    user_id: UUID,
    upload: UploadFile,
    *,
    fallback_name: str,
):
    filename = upload.filename or fallback_name
    return await file_service.upload(
        actor_id=user_id,
        content=await upload.read(),
        original_name=filename,
        display_name=filename,
        extension=_upload_extension(upload.filename),
        mime_type=upload.content_type or "application/octet-stream",
    )


async def _archive_file_safely(
    file_service: FileService,
    file_id: UUID,
    user_id: UUID,
) -> bool:
    try:
        await file_service.archive(file_id=file_id, user_id=user_id)
    except Exception:
        logger.exception("Failed to archive replaced Schema file %s", file_id)
        return False
    return True


async def _archive_uploaded(
    file_service: FileService,
    file_ids: list[UUID],
    user_id: UUID,
) -> bool:
    succeeded = True
    for file_id in dict.fromkeys(file_ids):
        succeeded = await _archive_file_safely(
            file_service,
            file_id,
            user_id,
        ) and succeeded
    return succeeded


def _form_values(
    schema_number: str,
    schema_name: str,
    change_description: str,
    change_justification: str,
    upload_date: date,
) -> dict[str, str]:
    return {
        "schema_number": schema_number,
        "schema_name": schema_name,
        "change_description": change_description,
        "change_justification": change_justification,
        "upload_date": upload_date.isoformat(),
    }


def _record_value_error_status(exc: ValueError) -> int:
    if "не найдена" in str(exc).lower():
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST


async def _get_active_record(
    schema_service: SchemaService,
    user_id: UUID,
    urza_id: UUID,
    record_id: UUID,
) -> SchemaRecord:
    records = await schema_service.get_records(user_id, urza_id)
    record = next((item for item in records if item.id == record_id), None)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись схемы не найдена.",
        )
    return record


@router.get("/urza/{urza_id}/schemas")
async def get_urza_schemas(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    try:
        return await _render_schemes(
            request,
            urza_id,
            current_user,
            schema_service,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/urza/{urza_id}/schemas/new")
async def get_new_urza_schema_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
    task_id: UUID | None = None,
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    if task_id is not None:
        try:
            await schema_service.validate_task_for_result(
                user_id=current_user.id,
                urza_id=urza_id,
                task_id=task_id,
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
    return await _render_schema_form(
        request,
        urza_id,
        task_id=task_id,
    )


@router.post("/urza/{urza_id}/schemas")
async def create_urza_schema_record(
    request: Request,
    urza_id: UUID,
    schema_number: Annotated[str, Form()],
    schema_name: Annotated[str, Form()],
    change_description: Annotated[str, Form()],
    change_justification: Annotated[str, Form()],
    upload_date: Annotated[date, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    signed_form_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    scan_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    editable_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    task_id: Annotated[UUID | None, Form()] = None,
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    values = _form_values(
        schema_number,
        schema_name,
        change_description,
        change_justification,
        upload_date,
    )
    if signed_form_file is None or not signed_form_file.filename:
        return await _render_schema_form(
            request,
            urza_id,
            task_id=task_id,
            form_values=values,
            error_message="Загрузите подписанный формуляр схемы.",
            response_status=422,
        )

    uploaded: dict[str, UUID] = {}
    try:
        uploaded["signed_form_file_id"] = (
            await _upload_file(
                file_service,
                current_user.id,
                signed_form_file,
                fallback_name="Подписанный формуляр схемы",
            )
        ).id
        if scan_file is not None and scan_file.filename:
            uploaded["scan_file_id"] = (
                await _upload_file(
                    file_service,
                    current_user.id,
                    scan_file,
                    fallback_name="Скан схемы",
                )
            ).id
        if editable_file is not None and editable_file.filename:
            uploaded["editable_file_id"] = (
                await _upload_file(
                    file_service,
                    current_user.id,
                    editable_file,
                    fallback_name="Редактируемая схема",
                )
            ).id
    except Exception:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        logger.exception("Failed to upload Schema files")
        return await _render_schema_form(
            request,
            urza_id,
            task_id=task_id,
            form_values=values,
            error_message="Не удалось загрузить файлы схемы.",
            response_status=400,
        )

    try:
        await schema_service.create(
            user_id=current_user.id,
            urza_id=urza_id,
            schema_number=schema_number,
            schema_name=schema_name,
            change_description=change_description,
            change_justification=change_justification,
            upload_date=upload_date,
            signed_form_file_id=uploaded["signed_form_file_id"],
            scan_file_id=uploaded.get("scan_file_id"),
            editable_file_id=uploaded.get("editable_file_id"),
            task_id=task_id,
        )
    except (ValueError, PermissionError) as exc:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        code = 403 if isinstance(exc, PermissionError) else 400
        return await _render_schema_form(
            request,
            urza_id,
            task_id=task_id,
            form_values=values,
            error_message=str(exc),
            response_status=code,
        )
    except Exception:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        logger.exception("Failed to create Schema record")
        return await _render_schema_form(
            request,
            urza_id,
            task_id=task_id,
            form_values=values,
            error_message="Не удалось сохранить запись схемы.",
            response_status=500,
        )

    return await _render_schemes(request, urza_id, current_user, schema_service)


@router.get("/urza/{urza_id}/schemas/{record_id}/edit")
async def get_edit_urza_schema_form(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    record = await _get_active_record(
        schema_service,
        current_user.id,
        urza_id,
        record_id,
    )
    actions = await schema_service.get_available_actions(current_user.id, record)
    if "edit" not in actions:
        raise HTTPException(
            status_code=403,
            detail="Редактировать можно только доступный черновик схемы.",
        )
    return await _render_schema_form(request, urza_id, record=record)


@router.post("/urza/{urza_id}/schemas/{record_id}")
async def update_urza_schema_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    schema_number: Annotated[str, Form()],
    schema_name: Annotated[str, Form()],
    change_description: Annotated[str, Form()],
    change_justification: Annotated[str, Form()],
    upload_date: Annotated[date, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    signed_form_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    scan_file: Annotated[UploadFile | None, FastAPIFile()] = None,
    editable_file: Annotated[UploadFile | None, FastAPIFile()] = None,
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    record = await _get_active_record(
        schema_service,
        current_user.id,
        urza_id,
        record_id,
    )
    actions = await schema_service.get_available_actions(current_user.id, record)
    if "edit" not in actions:
        raise HTTPException(
            status_code=403,
            detail="Редактировать можно только доступный черновик схемы.",
        )

    values = _form_values(
        schema_number,
        schema_name,
        change_description,
        change_justification,
        upload_date,
    )
    previous_ids = {
        "signed_form_file_id": record.signed_form_file_id,
        "scan_file_id": record.scan_file_id,
        "editable_file_id": record.editable_file_id,
    }
    uploads = {
        "signed_form_file_id": signed_form_file,
        "scan_file_id": scan_file,
        "editable_file_id": editable_file,
    }
    uploaded: dict[str, UUID] = {}
    try:
        for field, upload in uploads.items():
            if upload is not None and upload.filename:
                uploaded[field] = (
                    await _upload_file(
                        file_service,
                        current_user.id,
                        upload,
                        fallback_name=field,
                    )
                ).id
    except Exception:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        logger.exception("Failed to upload replacement Schema files")
        return await _render_schema_form(
            request,
            urza_id,
            record=record,
            form_values=values,
            error_message="Не удалось загрузить новые файлы схемы.",
            response_status=400,
        )

    try:
        await schema_service.update(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
            schema_number=schema_number,
            schema_name=schema_name,
            change_description=change_description,
            change_justification=change_justification,
            upload_date=upload_date,
            signed_form_file_id=uploaded.get("signed_form_file_id"),
            scan_file_id=uploaded.get("scan_file_id", previous_ids["scan_file_id"]),
            editable_file_id=uploaded.get(
                "editable_file_id",
                previous_ids["editable_file_id"],
            ),
        )
    except (ValueError, PermissionError) as exc:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        code = 403 if isinstance(exc, PermissionError) else _record_value_error_status(exc)
        return await _render_schema_form(
            request,
            urza_id,
            record=record,
            form_values=values,
            error_message=str(exc),
            response_status=code,
        )
    except Exception:
        await _archive_uploaded(file_service, list(uploaded.values()), current_user.id)
        logger.exception("Failed to update Schema record")
        return await _render_schema_form(
            request,
            urza_id,
            record=record,
            form_values=values,
            error_message="Не удалось сохранить изменения схемы.",
            response_status=500,
        )

    retained_ids = {
        record.signed_form_file_id,
        record.scan_file_id,
        record.editable_file_id,
    }
    replaced_ids = {
        file_id
        for field, file_id in previous_ids.items()
        if file_id is not None and file_id not in retained_ids
    }
    notice = None
    if replaced_ids and not await _archive_uploaded(
        file_service,
        list(replaced_ids),
        current_user.id,
    ):
        notice = (
            "Изменение сохранено, но один из прежних файлов не удалось "
            "архивировать. Обратитесь к администратору."
        )
    return await _render_schemes(
        request,
        urza_id,
        current_user,
        schema_service,
        notice_message=notice,
    )


async def _run_workflow_action(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: User,
    schema_service: SchemaService,
    action: str,
):
    method = {
        "submit": schema_service.submit_for_review,
        "approve": schema_service.approve,
        "return": schema_service.return_to_draft,
    }[action]
    try:
        await method(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=_record_value_error_status(exc),
            detail=str(exc),
        ) from exc
    return await _render_schemes(request, urza_id, current_user, schema_service)


@router.post("/urza/{urza_id}/schemas/{record_id}/submit")
async def submit_urza_schema_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, schema_service, "submit"
    )


@router.post("/urza/{urza_id}/schemas/{record_id}/approve")
async def approve_urza_schema_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, schema_service, "approve"
    )


@router.post("/urza/{urza_id}/schemas/{record_id}/return")
async def return_urza_schema_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, schema_service, "return"
    )


@router.post("/urza/{urza_id}/schemas/{record_id}/delete")
async def delete_urza_schema_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    try:
        await schema_service.delete(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=_record_value_error_status(exc),
            detail=str(exc),
        ) from exc
    return await _render_schemes(request, urza_id, current_user, schema_service)
