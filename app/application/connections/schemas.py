from uuid import UUID

from pydantic import BaseModel


class ConnectionListItem(BaseModel):
    id: UUID
    dispatch_name: str
    sap_code: str | None
    asureo_code: str | None
    rdu_subordination: bool


class ConnectionDetails(BaseModel):
    id: UUID
    dispatch_name: str
    sap_code: str | None
    asureo_code: str | None
    rdu_subordination: bool