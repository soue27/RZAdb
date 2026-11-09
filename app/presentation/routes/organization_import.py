"""Маршруты предварительной проверки и подтверждения импорта организационной структуры."""


from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.templating import Jinja2Templates

from app.application.imports.organization import OrganizationImportService
from app.domain.user import User
from app.presentation.auth.dependencies import require_superadmin
from app.presentation.dependencies.services import (
    get_organization_import_service,
)
from app.presentation.file_uploads import read_upload_content

router = APIRouter(
    prefix="/organization-import",
    tags=["organization-import"],
)

templates = Jinja2Templates(directory="app/presentation/templates")


def _render_result(
    request: Request,
    *,
    result: dict,
    current_user: User,
):
    return templates.TemplateResponse(
        request=request,
        name="organization_import/result.html",
        context={
            "result": result,
            "current_user": current_user,
        },
    )


@router.post("/preview")
async def preview_organization_import(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    service: Annotated[
        OrganizationImportService,
        Depends(get_organization_import_service),
    ],
    file: Annotated[UploadFile, File()],
):
    """Проверяет XLSX-файл организационной структуры и показывает план изменений без записи в БД.
    """
    content = await read_upload_content(file)

    result = await service.preview(content=content)

    return _render_result(
        request,
        result=result,
        current_user=current_user,
    )


@router.post("/confirm")
async def confirm_organization_import(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    service: Annotated[
        OrganizationImportService,
        Depends(get_organization_import_service),
    ],
    file: Annotated[UploadFile, File()],
):
    """Повторно проверяет файл и подтверждает создание организационных узлов.
    """
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
