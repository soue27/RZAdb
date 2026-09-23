from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import Response

from app.application.files.service import FileService
from app.presentation.dependencies.services import get_file_service
from app.presentation.schemas.files import FileResponse

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileResponse)
async def upload_file(
    file: Annotated[UploadFile, FastAPIFile()],
    display_name: Annotated[str, Form()],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileResponse:
    content = await file.read()

    extension = ""
    if file.filename and "." in file.filename:
        extension = "." + file.filename.rsplit(".", 1)[1]

    saved_file = await file_service.upload(
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
    file_service: FileService,
    disposition: str,
) -> Response:
    try:
        file, content = await file_service.download(file_id=file_id)
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
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> Response:
    return await _get_file_response(
        file_id=file_id,
        file_service=file_service,
        disposition="inline",
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> Response:
    return await _get_file_response(
        file_id=file_id,
        file_service=file_service,
        disposition="attachment",
    )