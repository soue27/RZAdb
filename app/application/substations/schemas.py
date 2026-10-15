from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import HighestVoltage, OperationalCurrentType


class SubstationDetails(BaseModel):
    id: UUID
    dispatch_name: str
    highest_voltage: HighestVoltage
    operational_current_type: OperationalCurrentType
    sap_code: str | None
    asureo_code: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None


class SubstationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dispatch_name: str = Field(min_length=1, max_length=255)
    highest_voltage: HighestVoltage
    operational_current_type: OperationalCurrentType
    sap_code: str | None = Field(default=None, max_length=64)
    asureo_code: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=500)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    @field_validator("sap_code", "asureo_code", "address", mode="before")
    @classmethod
    def empty_optional_strings_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value
