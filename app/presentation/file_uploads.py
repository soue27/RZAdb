
from fastapi import UploadFile

from app.application.files import validation


async def read_upload_content(upload: UploadFile) -> bytes:
    """Проверяет файл до чтения и ограничивает объём прочитанных данных."""
    filename = upload.filename or ""

    validation.validate_upload(filename=filename)

    # Starlette обычно знает размер после разбора multipart-запроса.
    # Но не полагаемся только на это значение.
    if (
        upload.size is not None
        and upload.size > validation.MAX_FILE_SIZE_BYTES
    ):
        validation.validate_upload(
            filename=filename,
            content_size=upload.size,
        )

    # Читаем максимум на один байт больше лимита, чтобы обнаружить превышение.
    content = await upload.read(validation.MAX_FILE_SIZE_BYTES + 1)

    validation.validate_upload(
        filename=filename,
        content_size=len(content),
    )

    return content
