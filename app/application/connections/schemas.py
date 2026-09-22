from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import OperationalCurrentType


class ConnectionListItem(BaseModel):
    id: UUID
    dispatch_name: str
    sap_code: str | None
    asureo_code: str | None
    rdu_subordination: bool
    operational_current_type: OperationalCurrentType


class ConnectionDetails(BaseModel):
    id: UUID
    dispatch_name: str
    sap_code: str | None
    asureo_code: str | None
    rdu_subordination: bool
    operational_current_type: OperationalCurrentType