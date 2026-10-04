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
from app.application.settings.service import SettingsService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_settings_service,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/objects", tags=["settings"])
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


async def _render_settings(
    request: Request,
    urza_id: UUID,
    current_user: User,
    settings_service: SettingsService,
    *,
    error_message: str | None = None,
    notice_message: str | None = None,
    response_status: int = status.HTTP_200_OK,
):
    settings_form, settings_records = await settings_service.get_details(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    current_approved = await settings_service.get_current_approved(
        user_id=current_user.id,
        urza_id=urza_id,
    )
    actions_by_record = {
        record.id: await settings_service.get_available_actions(
            user_id=current_user.id,
            record=record,
        )
        for record in settings_records
    }
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_settings.html",
        context={
            "settings_form": settings_form,
            "settings_records": settings_records,
            "current_approved": current_approved,
            "actions_by_record": actions_by_record,
            "current_user": current_user,
            "urza_id": urza_id,
            "error_message": error_message,
            "notice_message": notice_message,
        },
        status_code=response_status,
    )


def _upload_extension(filename: str | None) -> str:
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[1]
    return ""


def _settings_value_error_status(exc: ValueError) -> int:
    if "не найдена" in str(exc).lower():
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST


async def _upload_signed_form(
    file_service: FileService,
    user_id: UUID,
    signed_form_file: UploadFile,
):
    filename = signed_form_file.filename or "signed_form"
    return await file_service.upload(
        actor_id=user_id,
        content=await signed_form_file.read(),
        original_name=filename,
        display_name=filename if signed_form_file.filename else "Подписанный формуляр",
        extension=_upload_extension(signed_form_file.filename),
        mime_type=signed_form_file.content_type or "application/octet-stream",
    )


async def _archive_file_safely(
    file_service: FileService,
    file_id: UUID,
    user_id: UUID,
) -> bool:
    try:
        await file_service.archive(file_id=file_id, user_id=user_id)
    except Exception:
        logger.exception("Failed to archive Settings signed-form file %s", file_id)
        return False
    return True


async def _render_settings_form(
    request: Request,
    urza_id: UUID,
    *,
    record=None,
    error_message: str | None = None,
    form_values: dict | None = None,
    response_status: int = status.HTTP_200_OK,
):
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_settings_form.html",
        context={
            "urza_id": urza_id,
            "record": record,
            "form_values": form_values or {},
            "error_message": error_message,
            "is_edit": record is not None,
        },
        status_code=response_status,
    )


@router.get("/urza/{urza_id}/settings")
async def get_urza_settings(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    try:
        return await _render_settings(
            request, urza_id, current_user, settings_service
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/urza/{urza_id}/settings/new")
async def get_new_urza_settings_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    return await _render_settings_form(request, urza_id)


@router.post("/urza/{urza_id}/settings")
async def create_urza_settings_record(
    request: Request,
    urza_id: UUID,
    change_date: Annotated[date, Form()],
    parameter_name: Annotated[str, Form()],
    initial_setting: Annotated[str, Form()],
    new_setting: Annotated[str, Form()],
    change_reason: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    signed_form_file: Annotated[UploadFile | None, FastAPIFile()] = None,
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    form_values = {
        "change_date": change_date.isoformat(),
        "parameter_name": parameter_name,
        "initial_setting": initial_setting,
        "new_setting": new_setting,
        "change_reason": change_reason,
    }
    if signed_form_file is None or not signed_form_file.filename:
        return await _render_settings_form(
            request,
            urza_id,
            error_message="Загрузите подписанный формуляр.",
            form_values=form_values,
            response_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        saved_file = await _upload_signed_form(
            file_service, current_user.id, signed_form_file
        )
    except Exception as exc:
        logger.exception("Failed to upload Settings signed form")
        return await _render_settings_form(
            request,
            urza_id,
            error_message="Не удалось загрузить подписанный формуляр.",
            form_values=form_values,
            response_status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        await settings_service.create_record(
            user_id=current_user.id,
            urza_id=urza_id,
            change_date=change_date,
            parameter_name=parameter_name,
            initial_setting=initial_setting,
            new_setting=new_setting,
            change_reason=change_reason,
            signed_form_file_id=saved_file.id,
        )
    except (ValueError, PermissionError) as exc:
        await _archive_file_safely(file_service, saved_file.id, current_user.id)
        error_status = 403 if isinstance(exc, PermissionError) else 400
        return await _render_settings_form(
            request,
            urza_id,
            error_message=str(exc),
            form_values=form_values,
            response_status=error_status,
        )
    except Exception:
        await _archive_file_safely(file_service, saved_file.id, current_user.id)
        logger.exception("Failed to create Settings record")
        return await _render_settings_form(
            request,
            urza_id,
            error_message="Не удалось сохранить изменение уставок.",
            form_values=form_values,
            response_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return await _render_settings(
        request, urza_id, current_user, settings_service
    )


@router.get("/urza/{urza_id}/settings/{record_id}/edit")
async def get_edit_urza_settings_form(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    _, records = await settings_service.get_details(current_user.id, urza_id)
    record = next((item for item in records if item.id == record_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Запись уставок не найдена.")
    actions = await settings_service.get_available_actions(current_user.id, record)
    if "edit" not in actions:
        raise HTTPException(
            status_code=403,
            detail="Редактировать можно только доступный черновик уставок.",
        )
    return await _render_settings_form(request, urza_id, record=record)


@router.post("/urza/{urza_id}/settings/{record_id}")
async def update_urza_settings_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    change_date: Annotated[date, Form()],
    parameter_name: Annotated[str, Form()],
    initial_setting: Annotated[str, Form()],
    new_setting: Annotated[str, Form()],
    change_reason: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    signed_form_file: Annotated[UploadFile | None, FastAPIFile()] = None,
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    _, records = await settings_service.get_details(current_user.id, urza_id)
    record = next((item for item in records if item.id == record_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Запись уставок не найдена.")

    form_values = {
        "change_date": change_date.isoformat(),
        "parameter_name": parameter_name,
        "initial_setting": initial_setting,
        "new_setting": new_setting,
        "change_reason": change_reason,
    }
    new_file = None
    old_file_id = record.signed_form_file_id
    if signed_form_file is not None and signed_form_file.filename:
        try:
            new_file = await _upload_signed_form(
                file_service, current_user.id, signed_form_file
            )
        except Exception:
            logger.exception("Failed to upload replacement Settings signed form")
            return await _render_settings_form(
                request,
                urza_id,
                record=record,
                form_values=form_values,
                error_message="Не удалось загрузить новый подписанный формуляр.",
                response_status=400,
            )

    try:
        await settings_service.update_draft(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
            change_date=change_date,
            parameter_name=parameter_name,
            initial_setting=initial_setting,
            new_setting=new_setting,
            change_reason=change_reason,
            signed_form_file_id=new_file.id if new_file else None,
        )
    except (ValueError, PermissionError) as exc:
        if new_file:
            await _archive_file_safely(file_service, new_file.id, current_user.id)
        error_status = (
            status.HTTP_403_FORBIDDEN
            if isinstance(exc, PermissionError)
            else _settings_value_error_status(exc)
        )
        return await _render_settings_form(
            request,
            urza_id,
            record=record,
            form_values=form_values,
            error_message=str(exc),
            response_status=error_status,
        )
    except Exception:
        if new_file:
            await _archive_file_safely(file_service, new_file.id, current_user.id)
        logger.exception("Failed to update Settings record")
        return await _render_settings_form(
            request,
            urza_id,
            record=record,
            form_values=form_values,
            error_message="Не удалось сохранить изменение уставок.",
            response_status=500,
        )

    notice_message = None
    if new_file and old_file_id and old_file_id != new_file.id:
        if not await _archive_file_safely(file_service, old_file_id, current_user.id):
            notice_message = (
                "Изменение сохранено, но прежний файл не удалось архивировать. "
                "Обратитесь к администратору."
            )
    return await _render_settings(
        request,
        urza_id,
        current_user,
        settings_service,
        notice_message=notice_message,
    )


async def _run_workflow_action(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: User,
    settings_service: SettingsService,
    action: str,
):
    method = {
        "submit": settings_service.submit_for_review,
        "approve": settings_service.approve,
        "return": settings_service.return_to_draft,
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
            status_code=_settings_value_error_status(exc), detail=str(exc)
        ) from exc
    return await _render_settings(request, urza_id, current_user, settings_service)


@router.post("/urza/{urza_id}/settings/{record_id}/submit")
async def submit_urza_settings_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, settings_service, "submit"
    )


@router.post("/urza/{urza_id}/settings/{record_id}/approve")
async def approve_urza_settings_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, settings_service, "approve"
    )


@router.post("/urza/{urza_id}/settings/{record_id}/return")
async def return_urza_settings_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    return await _run_workflow_action(
        request, urza_id, record_id, current_user, settings_service, "return"
    )


@router.post("/urza/{urza_id}/settings/{record_id}/delete")
async def delete_urza_settings_record(
    request: Request,
    urza_id: UUID,
    record_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
):
    await _check_urza_access(object_service, current_user.id, urza_id)
    try:
        await settings_service.delete_record(
            user_id=current_user.id,
            urza_id=urza_id,
            record_id=record_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _render_settings(request, urza_id, current_user, settings_service)
