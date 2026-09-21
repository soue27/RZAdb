from datetime import date
from uuid import UUID

from pydantic import BaseModel


class InspectionListItem(BaseModel):
    id: UUID
    substation_id: UUID
    inspection_date: date
    remarks: str
    created_by: UUID
    scan_file_id: UUID | None
    scan_file_name: str | None
    editable_file_id: UUID | None
    editable_file_name: str | None