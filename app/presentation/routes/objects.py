from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_object_service
from fastapi.templating import Jinja2Templates

router = APIRouter(
    prefix="/objects",
    tags=["objects"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)

@router.get("/{object_type}/{object_id}")
async def get_object(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
):
    try:
        selected_object = await object_service.get_object(
            user_id=current_user.id,
            object_type=object_type,
            object_id=object_id,
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
        name="objects/selected_object.html",
        context={
            "object": selected_object,
        },
    )