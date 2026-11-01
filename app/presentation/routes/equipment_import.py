from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.templating import Jinja2Templates

from app.application.imports.equipment import EquipmentImportService
from app.domain.enums import UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_equipment_import_service
from app.presentation.file_uploads import read_upload_content


router = APIRouter(prefix="/equipment-import", tags=["equipment-import"])

templates = Jinja2Templates(directory="app/presentation/templates")


async def _check_import_access(
    current_user: User,
) -> None:
    if current_user.role not in {
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    }:
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для импорта оборудования.",
        )


def _render_result(
    request: Request,
    *,
    result: dict,
    current_user: User,
):
    return templates.TemplateResponse(
        request=request,
        name="equipment_import/result.html",
        context={
            "result": result,
            "current_user": current_user,
        },
    )


@router.post("/preview")
async def preview_equipment_import(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        EquipmentImportService,
        Depends(get_equipment_import_service),
    ],
    file: Annotated[UploadFile, File()],
):
    await _check_import_access(current_user)

    content = await read_upload_content(file)

    result = await service.preview(
        content=content,
        actor_id=current_user.id,
    )

    return _render_result(
        request,
        result=result,
        current_user=current_user,
    )



@router.post("/confirm")
async def confirm_equipment_import(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        EquipmentImportService,
        Depends(get_equipment_import_service),
    ],
    file: Annotated[UploadFile, File()],
):
    await _check_import_access(current_user)

    content = await read_upload_content(file)

    result = await service.confirm(
        content=content,
        actor_id=current_user.id,
    )

    return _render_result(
        request,
        result=result,
        current_user=current_user,
    )