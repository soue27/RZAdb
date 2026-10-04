from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.schema.service import SchemaService
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_object_service,
    get_schema_service,
)
from app.domain.user import User


templates = Jinja2Templates(
    directory="app/presentation/templates",
)

router = APIRouter(
    prefix="/objects",
    tags=["objects"],
)


@router.get("/urza/{urza_id}/schemas")
async def get_urza_schemas(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
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

    schema_form, schema_records = await schema_service.get_details(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_schemas.html",
        context={
            "schema_form": schema_form,
            "schema_records": schema_records,
            "urza_id": urza_id,
            "current_user": current_user,
        },
    )


@router.get("/urza/{urza_id}/schemas/new")
async def get_new_urza_schema_form(
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
            detail="Недостаточно прав для добавления схемы.",
        )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_schemas_form.html",
        context={
            "urza_id": urza_id,
            "current_user": current_user,
        },
    )