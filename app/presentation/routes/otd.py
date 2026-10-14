from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.otd.service import OTDService
from app.application.tree.service import TreeService
from app.domain.enums import OTDPurpose
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_object_service,
    get_otd_service,
    get_tree_service,
)

router = APIRouter(prefix="/objects", tags=["otd"])
templates = Jinja2Templates(directory="app/presentation/templates")


async def _ensure_urza_access(
    object_service: ObjectService,
    user: User,
    urza_id: UUID,
) -> None:
    try:
        await object_service.get_object(
            user_id=user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc


async def _render_form(
    request: Request,
    user: User,
    tree_service: TreeService,
    *,
    urza_id: UUID,
    task_id: UUID | None,
    form_values: dict,
    has_otd: bool = False,
    error_message: str | None = None,
    status_code: int = 200,
):
    context = {
        "urza_id": urza_id,
        "task_id": task_id,
        "has_otd": has_otd,
        "purposes": list(OTDPurpose),
        "form_values": form_values,
        "error_message": error_message,
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_otd_form.html",
            context=context,
            status_code=status_code,
        )
    tree = await tree_service.get_tree(user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="objects/urza_otd_page.html",
        context={
            **context,
            "current_user": user,
            "tree": tree,
            "content_template": "objects/urza_otd_form.html",
        },
        status_code=status_code,
    )


@router.get("/urza/{urza_id}/otd/new")
async def get_otd_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    otd_service: Annotated[OTDService, Depends(get_otd_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    task_id: UUID | None = None,
):
    await _ensure_urza_access(object_service, current_user, urza_id)
    otd = await otd_service.get_by_urza(current_user.id, urza_id)
    if task_id is not None:
        try:
            await otd_service.validate_task_for_result(
                current_user.id, urza_id, task_id
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _render_form(
        request,
        current_user,
        tree_service,
        urza_id=urza_id,
        task_id=task_id,
        form_values={},
        has_otd=otd is not None,
    )


@router.post("/urza/{urza_id}/otd")
async def save_otd_version(
    request: Request,
    urza_id: UUID,
    effective_date: Annotated[date, Form()],
    urza_service_life: Annotated[int, Form()],
    urza_purpose: Annotated[OTDPurpose, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    otd_service: Annotated[OTDService, Depends(get_otd_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    panel_cabinet_type: Annotated[str | None, Form()] = None,
    panel_cabinet_serial: Annotated[str | None, Form()] = None,
    panel_cabinet_manufacture_year: Annotated[int | None, Form()] = None,
    terminal_type: Annotated[str | None, Form()] = None,
    terminal_serial: Annotated[str | None, Form()] = None,
    terminal_manufacture_year: Annotated[int | None, Form()] = None,
    software_version: Annotated[str | None, Form()] = None,
    ct_ratio: Annotated[str | None, Form()] = None,
    vt_ratio: Annotated[str | None, Form()] = None,
    urza_scheme_designation: Annotated[str | None, Form()] = None,
    task_id: Annotated[UUID | None, Form()] = None,
):
    await _ensure_urza_access(object_service, current_user, urza_id)
    form_values = {
        "effective_date": effective_date.isoformat(),
        "urza_service_life": str(urza_service_life),
        "urza_purpose": urza_purpose.value,
        "panel_cabinet_type": panel_cabinet_type or "",
        "panel_cabinet_serial": panel_cabinet_serial or "",
        "panel_cabinet_manufacture_year": panel_cabinet_manufacture_year or "",
        "terminal_type": terminal_type or "",
        "terminal_serial": terminal_serial or "",
        "terminal_manufacture_year": terminal_manufacture_year or "",
        "software_version": software_version or "",
        "ct_ratio": ct_ratio or "",
        "vt_ratio": vt_ratio or "",
        "urza_scheme_designation": urza_scheme_designation or "",
    }
    version_fields = {
        key: value
        for key, value in {
            "panel_cabinet_type": panel_cabinet_type,
            "panel_cabinet_serial": panel_cabinet_serial,
            "panel_cabinet_manufacture_year": panel_cabinet_manufacture_year,
            "terminal_type": terminal_type,
            "terminal_serial": terminal_serial,
            "terminal_manufacture_year": terminal_manufacture_year,
            "software_version": software_version,
            "ct_ratio": ct_ratio,
            "vt_ratio": vt_ratio,
            "urza_scheme_designation": urza_scheme_designation,
        }.items()
        if value is not None
    }
    otd = None
    try:
        otd = await otd_service.get_by_urza(current_user.id, urza_id)
        if otd is None:
            await otd_service.create(
                user_id=current_user.id,
                urza_id=urza_id,
                effective_date=effective_date,
                urza_service_life=urza_service_life,
                urza_purpose=urza_purpose,
                task_id=task_id,
                **version_fields,
            )
        else:
            await otd_service.create_version(
                user_id=current_user.id,
                otd_id=otd.id,
                effective_date=effective_date,
                urza_service_life=urza_service_life,
                urza_purpose=urza_purpose,
                task_id=task_id,
                **version_fields,
            )
    except PermissionError as exc:
        return await _render_form(
            request, current_user, tree_service,
            urza_id=urza_id, task_id=task_id, form_values=form_values,
            error_message=str(exc), status_code=403,
            has_otd=otd is not None,
        )
    except ValueError as exc:
        return await _render_form(
            request, current_user, tree_service,
            urza_id=urza_id, task_id=task_id, form_values=form_values,
            error_message=str(exc), status_code=400,
            has_otd=otd is not None,
        )

    destination = f"/objects/urza/{urza_id}?tab=otd"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": destination})
    return RedirectResponse(destination, status_code=303)


async def _transition(
    request: Request,
    user: User,
    object_service: ObjectService,
    otd_service: OTDService,
    urza_id: UUID,
    version_id: UUID,
    operation: str,
):
    await _ensure_urza_access(object_service, user, urza_id)
    actions = {
        "submit": otd_service.submit_for_review,
        "approve": otd_service.approve,
        "return": otd_service.return_to_draft,
    }
    try:
        await actions[operation](user.id, urza_id, version_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    destination = f"/objects/urza/{urza_id}?tab=otd"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": destination})
    return RedirectResponse(destination, status_code=303)


@router.post("/urza/{urza_id}/otd/{version_id}/submit")
async def submit_otd_version(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[OTDService, Depends(get_otd_service)],
):
    return await _transition(request, user, object_service, service, urza_id, version_id, "submit")


@router.post("/urza/{urza_id}/otd/{version_id}/approve")
async def approve_otd_version(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[OTDService, Depends(get_otd_service)],
):
    return await _transition(request, user, object_service, service, urza_id, version_id, "approve")


@router.post("/urza/{urza_id}/otd/{version_id}/return")
async def return_otd_version(
    request: Request,
    urza_id: UUID,
    version_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    service: Annotated[OTDService, Depends(get_otd_service)],
):
    return await _transition(request, user, object_service, service, urza_id, version_id, "return")
