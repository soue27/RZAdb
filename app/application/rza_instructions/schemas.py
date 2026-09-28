from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class RZAInstructionDetails(BaseModel):
    instruction_id: UUID
    version_id: UUID
    version_number: int
    effective_date: date
    change_description: str | None
    change_justification: str | None
    scan_file_id: UUID
    scan_file_name: str | None
    editable_file_id: UUID | None
    editable_file_name: str | None


class RZAInstructionVersionDetails(BaseModel):
    id: UUID
    version_number: int
    effective_date: date
    change_description: str | None
    change_justification: str | None
    created_at: datetime
    created_by_full_name: str | None
    scan_file_id: UUID
    scan_file_name: str | None
    editable_file_id: UUID | None
    editable_file_name: str | None