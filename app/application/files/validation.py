
from pathlib import PurePosixPath


MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

MIME_TYPES_BY_EXTENSION: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    # CAD and drawing formats without a dependable MIME type are stored as
    # generic binary content and are not rendered as active browser content.
    ".dwg": "application/octet-stream",
    ".dxf": "application/octet-stream",
    ".dgn": "application/octet-stream",
    ".dwf": "application/octet-stream",
    ".dwfx": "application/octet-stream",
    ".plt": "application/octet-stream",
    ".vsd": "application/octet-stream",
    ".vsdx": "application/octet-stream",
    ".odg": "application/octet-stream",
    ".step": "application/octet-stream",
    ".stp": "application/octet-stream",
    ".iges": "application/octet-stream",
    ".igs": "application/octet-stream",
    ".ifc": "application/octet-stream",
    ".svg": "application/octet-stream",
    ".eps": "application/octet-stream",
}


class FileUploadValidationError(ValueError):
    """Ошибка проверки загружаемого файла."""

    status_code = 400


class FileTooLargeError(FileUploadValidationError):
    """Размер файла превышает разрешённый."""

    status_code = 413


class UnsupportedFileTypeError(FileUploadValidationError):
    """Расширение файла не входит в разрешённый список."""

    status_code = 415


def validate_upload(
    *,
    filename: str,
    extension: str | None = None,
    content_size: int | None = None,
) -> str:
    """Проверяет имя, расширение и размер; возвращает расширение в нижнем регистре."""
    normalized_filename = filename.replace("\\", "/")
    actual_extension = PurePosixPath(normalized_filename).suffix.lower()

    if actual_extension not in MIME_TYPES_BY_EXTENSION:
        allowed = ", ".join(sorted(MIME_TYPES_BY_EXTENSION))
        raise UnsupportedFileTypeError(
            f"Формат файла не поддерживается. "
            f"Разрешены: {allowed}."
        )

    if extension:
        declared_extension = "." + extension.lstrip(".").lower()
        if declared_extension != actual_extension:
            raise UnsupportedFileTypeError(
                "Расширение файла не совпадает с указанным форматом."
            )

    if content_size is not None and content_size > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise FileTooLargeError(
            f"Файл превышает максимально допустимый размер {max_mb} МБ."
        )

    return actual_extension
