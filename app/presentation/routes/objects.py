from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates

from app.application.connections.service import ConnectionService
from app.application.inspections.inspection_service import InspectionService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.urzas.service import URZAService
from app.application.objects.service import ObjectService
from app.application.rza_instructions.service import RZAInstructionService
from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.application.substations.service import SubstationService
from app.application.urzas.service import URZAService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_connection_service,
    get_inspection_service,
    get_object_service,
    get_rza_instruction_service,
    get_selectivity_scheme_service,
    get_substation_service,
    get_urza_service,
)

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
                },
            )

        if object_type == "connection":
            connection = await connection_service.get_by_id(object_id)

            if connection is None:
                raise ObjectNotFoundError

            return templates.TemplateResponse(
                request=request,
                name="objects/connection.html",
                context={
                    "connection": connection,
                },
            )

        if object_type == "urza":
            urza = await urza_service.get_details(object_id)

            return templates.TemplateResponse(
                request=request,
                name="objects/urza.html",
                context={
                    "urza": urza,
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
        },
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

    return templates.TemplateResponse(
        request=request,
        name="objects/substation_instructions.html",
        context={"instruction": instruction},
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