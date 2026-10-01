from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi import Form, UploadFile
from fastapi import File as FastAPIFile
from fastapi.templating import Jinja2Templates


from app.application.files.service import FileService

from app.application.connections.service import ConnectionService
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
from app.application.substations.service import SubstationService
from app.application.urzas.service import URZAService
from app.application.maintenance.service import TORecordService
from app.domain.enums import ProgramType
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.application.schema.service import SchemaService
from app.application.programs.service import ProgramService
from app.application.urza_instructions.service import URZAInstructionService
from app.presentation.dependencies.services import (
    get_connection_service,
    get_inspection_service,
    get_object_service,
    get_otd_service,
    get_rza_instruction_service,
    get_selectivity_scheme_service,
    get_substation_service,
    get_urza_service,
    get_schema_service,
    get_maintenance_service,
    get_program_service,
    get_urza_instruction_service,
    get_file_service,
    get_settings_service,
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
    otd_service: Annotated[
        OTDService,
        Depends(get_otd_service),
    ],
    settings_service: Annotated[
        SettingsService,
        Depends(get_settings_service),
    ],
    otd_version: UUID | None = Query(default=None),
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

            otd = await otd_service.get_details(
                user_id=current_user.id,
                urza_id=object_id,
                version_id=otd_version,
            )

            settings_form, settings_records = await settings_service.get_details(
                user_id=current_user.id,
                urza_id=object_id,
            )

            return templates.TemplateResponse(
                request=request,
                name="objects/urza.html",
                context={
                    "urza": urza,
                    "otd": otd,
                    "settings_form": settings_form,
                    "settings_records": settings_records,
                    "current_user": current_user,
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


@router.get("/urza/{urza_id}/schemas")
async def get_urza_schemas(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    schema_service: Annotated[
        SchemaService,
        Depends(get_schema_service),
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
        },
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

    maintenance_records = await maintenance_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_maintenance.html",
        context={
            "maintenance_records": maintenance_records,
        },
    )


@router.get("/urza/{urza_id}/programs")
async def get_urza_programs(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
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

    programs = await program_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs.html",
        context={
            "programs": programs,
            "urza_id": urza_id,
        },
    )


@router.get("/urza/{urza_id}/programs/new")
async def get_new_urza_program_form(
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

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_program_form.html",
        context={
            "urza_id": urza_id,
            "program_types": list(ProgramType),
        },
    )


@router.post("/urza/{urza_id}/programs")
async def create_urza_program(
    request: Request,
    urza_id: UUID,
    program_type: Annotated[ProgramType, Form()],
    program_number: Annotated[str, Form()],
    scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
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

    scan_content = await scan_file.read()

    saved_scan = await file_service.upload(
        actor_id=current_user.id,
        content=scan_content,
        original_name=scan_file.filename or "scan",
        display_name=scan_file.filename or "Скан программы",
        extension=(
            "." + scan_file.filename.rsplit(".", 1)[1]
            if scan_file.filename and "." in scan_file.filename
            else ""
        ),
        mime_type=scan_file.content_type or "application/octet-stream",
    )

    editable_file_id = None

    if editable_file and editable_file.filename:
        editable_content = await editable_file.read()

        saved_editable = await file_service.upload(
            actor_id=current_user.id,
            content=editable_content,
            original_name=editable_file.filename,
            display_name=editable_file.filename,
            extension=(
                "." + editable_file.filename.rsplit(".", 1)[1]
                if "." in editable_file.filename
                else ""
            ),
            mime_type=editable_file.content_type or "application/octet-stream",
        )

        editable_file_id = saved_editable.id

    await program_service.create(
        user_id=current_user.id,
        urza_id=urza_id,
        program_type=program_type,
        program_number=program_number,
        scan_file_id=saved_scan.id,
        editable_file_id=editable_file_id,
    )

    programs = await program_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs.html",
        context={
            "programs": programs,
            "urza_id": urza_id,
        },
    )


@router.get("/urza/{urza_id}/instruction")
async def get_urza_instruction(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    urza_instruction_service: Annotated[
        URZAInstructionService,
        Depends(get_urza_instruction_service),
    ],
    instruction_version: UUID | None = Query(default=None),
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
            detail="Доступ запрещён",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URZA не найдено",
        ) from exc

    instruction = await urza_instruction_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    versions = []
    selected_version = None

    if instruction is not None:
        versions = await urza_instruction_service.get_versions(
            user_id=current_user.id,
            urza_id=urza_id,
        )

        if instruction_version is not None:
            selected_version = await urza_instruction_service.get_version_by_id(
                user_id=current_user.id,
                version_id=instruction_version,
            )

        if selected_version is None and versions:
            selected_version = versions[0]

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_instruction.html",
        context={
            "instruction": instruction,
            "versions": versions,
            "selected_version": selected_version,
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