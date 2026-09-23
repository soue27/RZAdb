from datetime import date
from uuid import UUID

from pydantic import BaseModel
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