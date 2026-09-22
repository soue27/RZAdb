from datetime import date
from uuid import UUID

from pydantic import BaseModel


class SelectivitySchemeDetails(BaseModel):
    scheme_id: UUID
    version_id: UUID
    version_number: int
    number: str
    name: str
    effective_date: date
    change_description: str | None
    change_justification: str | None
    created_by: UUID
    creator_name: str | None
    scan_file_id: UUID
    scan_file_name: str | None
    editable_file_id: UUID | None
    editable_file_name: str | None


class SelectivitySchemeVersionListItem(BaseModel):
    version_id: UUID
    version_number: int
    number: str
    name: str
    effective_date: date
    change_description: str | None
    change_justification: str | None
    created_by: UUID
    creator_name: str | None
    scan_file_id: UUID
    scan_file_name: str | None
    editable_file_id: UUID | None
    editable_file_name: str | None