"""files: зависимости и DTO presentation-слоя."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileUploadForm(BaseModel):
    """Поля формы загрузки файла, передаваемые отдельно от бинарного содержимого.
    """
    display_name: str
    extension: str
    mime_type: str


class FileResponse(BaseModel):
    """Метаданные файла, возвращаемые presentation API.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    display_name: str
    extension: str
    size: int
    mime_type: str
    uploaded_at: datetime