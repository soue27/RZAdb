from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.urzas.schemas import URZACreate
from app.application.urzas.service import (
    URZANameConflictError,
    URZAService,
)
from app.domain.enums import (
    ElementBase,
    RoomCategory,
    URZACategory,
    URZAStatus,
    UserRole,
)
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_object_service,
    get_urza_service,
)

router = APIRouter(prefix="/objects", tags=["urza-objects"])

templates = Jinja2Templates(directory="app/presentation/templates")

URZA_EDIT_ROLES = {
    UserRole.SUPERADMIN,
    UserRole.ADMIN,
    UserRole.MANAGER,
}


def _require_urza_edit_role(current_user: User) -> None:
    if current_user.role not in URZA_EDIT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для редактирования УРЗА.",
        )


async def _check_urza_access(
    object_service: ObjectService,
    current_user: User,
    urza_id: UUID,
) -> None:
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён.",
        )
    except ObjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="УРЗА не найдено.",
        )


def _urza_form_values(urza) -> dict:
    return {
        "dispatch_name": urza.dispatch_name,
        "commissioning_date": urza.commissioning_date.isoformat(),
        "inventory_number": urza.inventory_number or "",
        "status": urza.status.value,
        "element_base": urza.element_base.value,
        "category": urza.category.value,
        "room_category": urza.room_category.value,
        "rdu_subordination": urza.rdu_subordination,
        "complexity": urza.complexity,
    }


def _urza_form_context(
    *,
    connection_id: UUID,
    form_values: dict,
    is_edit: bool,
    urza_id: UUID | None = None,
    error_message: str | None = None,
) -> dict:
    return {
        "connection_id": connection_id,
        "urza_id": urza_id,
        "form_values": form_values,
        "is_edit": is_edit,
        "error_message": error_message,
        "urza_statuses": list(URZAStatus),
        "element_bases": list(ElementBase),
        "urza_categories": list(URZACategory),
        "room_categories": list(RoomCategory),
    }


@router.get("/urza/{urza_id}/edit")
async def get_urza_edit_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    urza_service: Annotated[URZAService, Depends(get_urza_service)],
):
    _require_urza_edit_role(current_user)
    await _check_urza_access(object_service, current_user, urza_id)

    urza = await urza_service.get_details(urza_id)

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_form.html",
        context=_urza_form_context(
            connection_id=urza.connection.id,
            urza_id=urza_id,
            form_values=_urza_form_values(urza),
            is_edit=True,
        ),
    )


@router.post("/urza/{urza_id}/edit")
async def post_urza_edit_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    urza_service: Annotated[URZAService, Depends(get_urza_service)],
    dispatch_name: Annotated[str, Form()] = "",
    commissioning_date: Annotated[str, Form()] = "",
    inventory_number: Annotated[str, Form()] = "",
    status_value: Annotated[str, Form(alias="status")] = "",
    element_base: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    room_category: Annotated[str, Form()] = "",
    rdu_subordination: Annotated[str, Form()] = "",
    complexity: Annotated[str, Form()] = "",
):
    _require_urza_edit_role(current_user)
    await _check_urza_access(object_service, current_user, urza_id)

    values = {
        "dispatch_name": dispatch_name,
        "commissioning_date": commissioning_date,
        "inventory_number": inventory_number or None,
        "status": status_value,
        "element_base": element_base,
        "category": category,
        "room_category": room_category,
        "rdu_subordination": rdu_subordination,
        "complexity": complexity,
    }

    urza = await urza_service.get_details(urza_id)

    async def render_form(error_message: str, response_status: int):
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_form.html",
            status_code=response_status,
            context=_urza_form_context(
                connection_id=urza.connection.id,
                urza_id=urza_id,
                form_values=values,
                is_edit=True,
                error_message=error_message,
            ),
        )

    try:
        data = URZACreate.model_validate(values)
    except ValidationError:
        return await render_form(
            "Проверьте введённые значения.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        await urza_service.update(
            urza_id=urza_id,
            actor_id=current_user.id,
            data=data,
        )
    except URZANameConflictError as exc:
        return await render_form(
            str(exc),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except ObjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="УРЗА не найдено.",
        )

    destination = f"/objects/urza/{urza_id}"

    if request.headers.get("HX-Request") == "true":
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
            headers={"HX-Redirect": destination},
        )

    return RedirectResponse(
        url=destination,
        status_code=status.HTTP_303_SEE_OTHER,
    )