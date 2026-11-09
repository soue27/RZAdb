from uuid import UUID

from pydantic import BaseModel


class SelectedObject(BaseModel):
    """Унифицированное краткое представление выбранного объекта для интерфейса.
    """
    object_type: str
    id: UUID
    name: str
    is_archived: bool = False
