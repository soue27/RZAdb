from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    substation_id: UUID


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dispatch_name: str = Field(min_length=1, max_length=255)
    rdu_subordination: bool
    sap_code: str | None = Field(default=None, max_length=64)
    asureo_code: str | None = Field(default=None, max_length=64)

    @field_validator("sap_code", "asureo_code", mode="before")
    @classmethod
    def empty_optional_codes_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ConnectionUpdate(ConnectionCreate):
    """Данные для обновления присоединения."""