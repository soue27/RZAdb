import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import Response

from app.application.files.access_service import FileAccessService
from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.service import FileService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_access_service,
    get_file_service,
)
from app.presentation.schemas.files import FileResponse

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)


@router.post("", response_model=FileResponse)
async def upload_file(
    file: Annotated[UploadFile, FastAPIFile()],
    display_name: Annotated[str, Form()],
    file_service: Annotated[FileService, Depends(get_file_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    content = await file.read()

    extension = ""
    if file.filename and "." in file.filename:
        extension = "." + file.filename.rsplit(".", 1)[1]

    saved_file = await file_service.upload(
        actor_id=current_user.id,
        content=content,
        original_name=file.filename or "file",
        display_name=display_name,
        extension=extension,
        mime_type=file.content_type or "application/octet-stream",
    )

    return FileResponse.model_validate(saved_file)


async def _get_file_response(
    *,
    file_id: UUID,
    current_user: User,
    file_access_service: FileAccessService,
    file_service: FileService,
    disposition: str,
) -> Response:
    try:
        file = await file_access_service.get_accessible_file(
            user_id=current_user.id,
            file_id=file_id,
        )
    except AmbiguousFileOwnershipError:
        logger.exception("Ambiguous ownership detected while accessing a file.")
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера.",
        ) from None
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Файл не найден.",
        ) from exc
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=403,
            detail="Доступ к файлу запрещён.",
        ) from exc

    try:
        content = await file_service.read(file)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Файл не найден.",
        ) from exc

    return Response(
        content=content,
        media_type=file.mime_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{file.original_name}"'
            ),
        },
    )


@router.get("/{file_id}/view")
async def view_file(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    file_access_service: Annotated[
        FileAccessService,
        Depends(get_file_access_service),
    ],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> Response:
    return await _get_file_response(
        file_id=file_id,
        current_user=current_user,
        file_access_service=file_access_service,
        file_service=file_service,
        disposition="inline",
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    file_access_service: Annotated[
        FileAccessService,
        Depends(get_file_access_service),
    ],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> Response:
    return await _get_file_response(
        file_id=file_id,
        current_user=current_user,
        file_access_service=file_access_service,
        file_service=file_service,
        disposition="attachment",
    )
