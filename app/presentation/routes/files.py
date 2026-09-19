from typing import Annotated

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi import File as FastAPIFile

from app.application.files.service import FileService
from app.presentation.dependencies import get_file_service
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