from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EnterpriseDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    short_name: str
    sap_code: str | None


class EnterpriseUpdate(BaseModel):
    @field_validator("sap_code", mode="before")

    @classmethod
    def empty_sap_code_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: str = Field(min_length=1, max_length=255)
    short_name: str = Field(min_length=1, max_length=255)
    sap_code: str | None = Field(default=None, max_length=64)