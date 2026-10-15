from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.application.connections.schemas import ConnectionCreate
from app.application.connections.service import (
    ConnectionNameConflictError,
    ConnectionService,
)
from app.application.inspections.inspection_service import InspectionService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.otd.service import OTDService
from app.application.rza_instructions.service import RZAInstructionService
from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.application.settings.service import SettingsService
from app.application.substations.schemas import SubstationUpdate
from app.application.substations.service import SubstationService
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.application.urzas.service import URZAService
from app.domain.enums import HighestVoltage, OperationalCurrentType, UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_connection_service,
    get_inspection_service,
    get_object_service,
    get_otd_service,
    get_rza_instruction_service,
    get_selectivity_scheme_service,
    get_settings_service,
    get_substation_service,
    get_task_service,
    get_tree_service,
    get_urza_service,
)

router = APIRouter(
    prefix="/objects",
    tags=["objects"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)

CONNECTION_CREATE_ROLES = {
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.SUPERADMIN,
}


def can_edit_substation(user: User) -> bool:
    return user.role in {
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.SUPERADMIN,
    }


@router.get("/{object_type}/{object_id}")
async def get_object(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[
        SubstationService,
        Depends(get_substation_service),
    ],
    connection_service: Annotated[
        ConnectionService,
        Depends(get_connection_service),
    ],
    urza_service: Annotated[
        URZAService,
        Depends(get_urza_service),
    ],
    otd_service: Annotated[
        OTDService,
        Depends(get_otd_service),
    ],
    settings_service: Annotated[
        SettingsService,
        Depends(get_settings_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    otd_version: UUID | None = Query(default=None),
    tab: str | None = Query(default=None),
):
    try:
        selected_object = await object_service.get_object(
            user_id=current_user.id,
            object_type=object_type,
            object_id=object_id,
        )

        if object_type == "substation":
            substation = await substation_service.get_details(object_id)

            return templates.TemplateResponse(
                request=request,
                name="objects/substation.html",
                context={
                    "substation": substation,
                    "can_edit": can_edit_substation(current_user),
                    "can_create_connection": current_user.role in CONNECTION_CREATE_ROLES,
                },
            )


        if object_type == "connection":
            connection = await connection_service.get_by_id(object_id)

            if connection is None:
                raise ObjectNotFoundError

            if request.headers.get("HX-Request") == "true":
                return templates.TemplateResponse(
                    request=request,
                    name="objects/connection.html",
                    context={"connection": connection},
                )

            tree = await tree_service.get_tree(user_id=current_user.id)
            return templates.TemplateResponse(
                request=request,
                name="objects/connection_page.html",
                context={
                    "connection": connection,
                    "current_user": current_user,
                    "tree": tree,
                    "page_title": connection.dispatch_name,
                    "content_template": "objects/connection.html",
                },
            )

        if object_type == "urza":
            urza = await urza_service.get_details(object_id)

            otd = await otd_service.get_details(
                user_id=current_user.id,
                urza_id=object_id,
                version_id=otd_version,
            )
            if otd_version is not None and (
                otd is None or otd.selected_version is None
            ):
                raise ObjectNotFoundError

            otd_versions = await otd_service.get_versions(
                current_user.id,
                object_id,
            )
            selected_otd_version = next(
                (
                    version
                    for version in otd_versions
                    if otd_version is not None and version.id == otd_version
                ),
                otd_versions[0] if otd_versions else None,
            )
            otd_actions = (
                await otd_service.get_available_actions(
                    current_user.id,
                    selected_otd_version,
                )
                if selected_otd_version is not None
                else set()
            )
            otd_create_actions = await otd_service.get_available_create_actions(
                current_user.id,
                object_id,
            )

            settings_form, settings_records = await settings_service.get_details(
                user_id=current_user.id,
                urza_id=object_id,
            )

            can_issue_task = await task_service.can_issue_task(
                actor_id=current_user.id,
                urza_id=object_id,
            )

            context = {
                "urza": urza,
                "otd": otd,
                "otd_actions": otd_actions,
                "otd_create_actions": otd_create_actions,
                "settings_form": settings_form,
                "settings_records": settings_records,
                "current_user": current_user,
                "active_tab": tab,
                "can_issue_task": can_issue_task,
            }

            if request.headers.get("HX-Request") == "true":
                return templates.TemplateResponse(
                    request=request,
                    name="objects/urza.html",
                    context=context,
                )

            tree = await tree_service.get_tree(user_id=current_user.id)
            return templates.TemplateResponse(
                request=request,
                name="objects/urza_page.html",
                context={
                    **context,
                    "tree": tree,
                },
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


@router.get("/substation/{substation_id}/inspections")
async def get_substation_inspections(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    inspection_service: Annotated[
        InspectionService,
        Depends(get_inspection_service),
    ],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="substation",
            object_id=substation_id,
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

    inspections = await inspection_service.get_by_substation_id(
        substation_id,
    )


    return templates.TemplateResponse(
        request=request,
        name="objects/substation_inspections.html",
        context={
            "inspections": inspections,
        },
    )








@router.get("/substation/{substation_id}/details")
async def get_substation_details(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[
        SubstationService,
        Depends(get_substation_service),
    ],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="substation",
            object_id=substation_id,
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

    substation = await substation_service.get_details(substation_id)

    return templates.TemplateResponse(
        request=request,
        name="objects/substation_details.html",
        context={
            "substation": substation,
            "can_edit": can_edit_substation(current_user),
        },
    )


def _substation_form_context(substation, current_user, **kwargs):
    return {
        "substation": substation,
        "current_user": current_user,
        "can_edit": can_edit_substation(current_user),
        "highest_voltages": list(HighestVoltage),
        "current_types": list(OperationalCurrentType),
        **kwargs,
    }


async def _check_substation_access(object_service, current_user, substation_id):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="substation",
            object_id=substation_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Доступ к объекту запрещён.") from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc


async def _get_accessible_substation(
    object_service,
    substation_service: SubstationService,
    current_user: User,
    substation_id: UUID,
):
    try:
        substation = await substation_service.get_details(substation_id)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Подстанция не найдена.") from exc
    await _check_substation_access(object_service, current_user, substation_id)
    return substation


def _require_connection_create_role(current_user: User) -> None:
    if current_user.role not in CONNECTION_CREATE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создавать присоединения с текущей ролью запрещено.",
        )


async def _render_connection_form(
    request: Request,
    substation_id: UUID,
    current_user: User,
    tree_service: TreeService,
    *,
    form_values: dict | None = None,
    error_message: str | None = None,
):
    context = {
        "substation_id": substation_id,
        "form_values": form_values or {},
        "error_message": error_message,
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/connection_form.html",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if error_message else status.HTTP_200_OK,
            context=context,
        )

    tree = await tree_service.get_tree(user_id=current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="objects/connection_page.html",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if error_message else status.HTTP_200_OK,
        context={
            **context,
            "current_user": current_user,
            "tree": tree,
            "page_title": "Добавление присоединения",
            "content_template": "objects/connection_form.html",
        },
    )


@router.get("/substation/{substation_id}/connections/new")
async def get_new_connection_form(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[SubstationService, Depends(get_substation_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    await _get_accessible_substation(
        object_service, substation_service, current_user, substation_id
    )
    _require_connection_create_role(current_user)
    return await _render_connection_form(
        request, substation_id, current_user, tree_service
    )


@router.post("/substation/{substation_id}/connections")
async def post_new_connection(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[SubstationService, Depends(get_substation_service)],
    connection_service: Annotated[ConnectionService, Depends(get_connection_service)],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
    dispatch_name: Annotated[str, Form()] = "",
    rdu_subordination: Annotated[str, Form()] = "",
    sap_code: Annotated[str, Form()] = "",
    asureo_code: Annotated[str, Form()] = "",
):
    await _get_accessible_substation(
        object_service, substation_service, current_user, substation_id
    )
    _require_connection_create_role(current_user)

    values = {
        "dispatch_name": dispatch_name,
        "rdu_subordination": rdu_subordination,
        "sap_code": sap_code,
        "asureo_code": asureo_code,
    }
    try:
        data = ConnectionCreate.model_validate(values)
    except ValidationError:
        return await _render_connection_form(
            request, substation_id, current_user, tree_service,
            form_values=values,
            error_message="Проверьте введённые значения.",
        )

    try:
        connection = await connection_service.create(
            substation_id=substation_id,
            actor_id=current_user.id,
            data=data,
        )
    except ConnectionNameConflictError as exc:
        return await _render_connection_form(
            request, substation_id, current_user, tree_service,
            form_values=values,
            error_message=str(exc),
        )

    destination = f"/objects/connection/{connection.id}"
    if request.headers.get("HX-Request") == "true":
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
            headers={"HX-Redirect": destination},
        )
    return RedirectResponse(
        url=destination,
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _require_substation_edit_role(current_user: User) -> None:
    if not can_edit_substation(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для редактирования.",
        )


@router.get("/substation/{substation_id}/edit")
async def get_substation_edit_form(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[SubstationService, Depends(get_substation_service)],
):
    await _check_substation_access(object_service, current_user, substation_id)
    _require_substation_edit_role(current_user)
    substation = await substation_service.get_details(substation_id)
    return templates.TemplateResponse(
        request=request,
        name="objects/substation_form.html",
        context=_substation_form_context(substation, current_user),
    )


@router.post("/substation/{substation_id}/edit")
async def post_substation_edit_form(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    substation_service: Annotated[SubstationService, Depends(get_substation_service)],
    dispatch_name: Annotated[str, Form()] = "",
    highest_voltage: Annotated[str, Form()] = "",
    operational_current_type: Annotated[str, Form()] = "",
    sap_code: Annotated[str, Form()] = "",
    asureo_code: Annotated[str, Form()] = "",
    address: Annotated[str, Form()] = "",
    latitude: Annotated[str, Form()] = "",
    longitude: Annotated[str, Form()] = "",
):
    await _check_substation_access(object_service, current_user, substation_id)
    _require_substation_edit_role(current_user)

    values = {
        "dispatch_name": dispatch_name,
        "highest_voltage": highest_voltage,
        "operational_current_type": operational_current_type,
        "sap_code": sap_code,
        "asureo_code": asureo_code,
        "address": address,
        "latitude": latitude or None,
        "longitude": longitude or None,
    }
    try:
        update = SubstationUpdate.model_validate(values)
    except ValidationError:
        substation = await substation_service.get_details(substation_id)
        return templates.TemplateResponse(
            request=request,
            name="objects/substation_form.html",
            status_code=422,
            context=_substation_form_context(
                substation, current_user, form_values=values,
                error_message="Проверьте введённые значения.",
            ),
        )

    substation = await substation_service.update_details(substation_id, update)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url=f"/objects/substation/{substation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return templates.TemplateResponse(
        request=request,
        name="objects/substation_details_fragment.html",
        context=_substation_form_context(substation, current_user),
    )


@router.get("/substation/{substation_id}/instructions")
async def get_substation_instructions(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    rza_instruction_service: Annotated[
        RZAInstructionService,
        Depends(get_rza_instruction_service),
    ],
    instruction_version: UUID | None = Query(default=None),
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="substation",
            object_id=substation_id,
        )
    except ObjectAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён.",
        )
    except ObjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подстанция не найдена.",
        )

    instruction = await rza_instruction_service.get_details(
        user_id=current_user.id,
        substation_id=substation_id,
    )

    versions = await rza_instruction_service.get_versions(
        user_id=current_user.id,
        substation_id=substation_id,
    )

    selected_version = None

    if instruction_version is not None:
        selected_version = next(
            (
                version
                for version in versions
                if version.id == instruction_version
            ),
            None,
        )

    if selected_version is None and versions:
        selected_version = versions[0]

    return templates.TemplateResponse(
        request=request,
        name="objects/substation_instructions.html",
        context={
            "instruction": instruction,
            "versions": versions,
            "selected_version": selected_version,
            "substation_id": substation_id,
        },
    )


@router.get("/substation/{substation_id}/selectivity-schemes")
async def get_substation_selectivity_schemes(
    request: Request,
    substation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[
        ObjectService,
        Depends(get_object_service),
    ],
    selectivity_scheme_service: Annotated[
        SelectivitySchemeService,
        Depends(get_selectivity_scheme_service),
    ],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="substation",
            object_id=substation_id,
        )
    except ObjectAccessDeniedError:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён.",
        )
    except ObjectNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Подстанция не найдена.",
        )

    versions = await selectivity_scheme_service.get_version_list(
        user_id=current_user.id,
        substation_id=substation_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/substation_selectivity_schemes.html",
        context={
            "versions": versions,
        },
    )
