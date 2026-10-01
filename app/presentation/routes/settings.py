from typing import Annotated
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status, Form
from fastapi import File as FastAPIFile, UploadFile
from fastapi.templating import Jinja2Templates

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.settings.service import SettingsService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.application.files.service import FileService
from app.presentation.dependencies.services import (
    get_object_service,
    get_settings_service,
    get_file_service,
)


router = APIRouter(
    prefix="/objects",
    tags=["settings"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)



@router.get("/urza/{urza_id}/settings")
async def get_urza_settings(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    settings_service: Annotated[
        SettingsService,
        Depends(get_settings_service),
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

    settings_form, settings_records = await settings_service.get_details(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_settings.html",
        context={
            "settings_form": settings_form,
            "settings_records": settings_records,
            "current_user": current_user,
            "urza_id": urza_id,
        },
    )


@router.post("/urza/{urza_id}/settings")
async def create_urza_settings_record(
    request: Request,
    urza_id: UUID,
    change_date: Annotated[date, Form()],
    parameter_name: Annotated[str, Form()],
    initial_setting: Annotated[str, Form()],
    new_setting: Annotated[str, Form()],
    change_reason: Annotated[str, Form()],
    signed_form_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    settings_service: Annotated[
        SettingsService,
        Depends(get_settings_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
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

    if current_user.role.value not in {
        "superadmin",
        "admin",
        "manager",
        "engineer",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для добавления записи.",
        )

    content = await signed_form_file.read()

    saved_file = await file_service.upload(
        actor_id=current_user.id,
        content=content,
        original_name=signed_form_file.filename or "signed_form",
        display_name=signed_form_file.filename or "Подписанная форма",
        extension=(
            "." + signed_form_file.filename.rsplit(".", 1)[1]
            if signed_form_file.filename and "." in signed_form_file.filename
            else ""
        ),
        mime_type=signed_form_file.content_type or "application/octet-stream",
    )

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

    settings_form, settings_records = await settings_service.get_details(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_settings.html",
        context={
            "settings_form": settings_form,
            "settings_records": settings_records,
            "current_user": current_user,
            "urza_id": urza_id,
        },
    )


@router.get("/urza/{urza_id}/settings/new")
async def get_new_urza_settings_form(
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

    if current_user.role.value not in {
        "superadmin",
        "admin",
        "manager",
        "engineer",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для добавления записи.",
        )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_settings_form.html",
        context={
            "urza_id": urza_id,
        },
    )
