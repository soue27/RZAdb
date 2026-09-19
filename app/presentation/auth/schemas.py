from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginForm(BaseModel):
    email: str
    password: str


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str