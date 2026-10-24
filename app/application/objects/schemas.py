from uuid import UUID

from pydantic import BaseModel


class SelectedObject(BaseModel):
    object_type: str
    id: UUID
    name: str
    is_archived: bool = False
