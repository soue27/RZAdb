from datetime import date
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