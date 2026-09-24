from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import OTDPurpose


class OTDVersionDetails(BaseModel):
    id: UUID
    version_number: int
    created_at: datetime
    effective_date: date

    panel_cabinet_type: str | None
    panel_cabinet_serial: str | None
    panel_cabinet_manufacture_year: int | None

    terminal_type: str | None
    terminal_serial: str | None
    terminal_manufacture_year: int | None

    urza_service_life: int
    software_version: str | None
    ct_ratio: str | None
    vt_ratio: str | None
    urza_scheme_designation: str | None
    urza_purpose: OTDPurpose


class OTDDetails(BaseModel):
    id: UUID
    current_version: OTDVersionDetails | None
    versions: list[OTDVersionDetails]