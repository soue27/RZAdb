from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    ElementBase,
    RoomCategory,
    URZACategory,
    URZAStatus,
)


class URZAConnectionInfo(BaseModel):
    id: UUID
    dispatch_name: str


class URZASubstationInfo(BaseModel):
    id: UUID
    dispatch_name: str


class URZACreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dispatch_name: str = Field(min_length=1, max_length=255)
    rdu_subordination: bool
    inventory_number: str | None = Field(default=None, max_length=64)
    commissioning_date: date
    status: URZAStatus
    element_base: ElementBase
    category: URZACategory
    room_category: RoomCategory
    complexity: bool

    @field_validator("inventory_number", mode="before")
    @classmethod
    def empty_inventory_number_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class URZADetails(BaseModel):
    id: UUID
    dispatch_name: str
    rdu_subordination: bool
    inventory_number: str | None
    commissioning_date: date
    status: URZAStatus
    element_base: ElementBase
    category: URZACategory
    room_category: RoomCategory
    complexity: bool

    connection: URZAConnectionInfo
    substation: URZASubstationInfo