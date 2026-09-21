from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import HighestVoltage


class SubstationDetails(BaseModel):
    id: UUID
    dispatch_name: str
    highest_voltage: HighestVoltage
    sap_code: str | None
    asureo_code: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None