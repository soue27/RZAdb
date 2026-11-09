"""schemas: зависимости и DTO presentation-слоя."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginForm(BaseModel):
    """Данные формы входа пользователя.
    """
    email: str
    password: str


class CurrentUserResponse(BaseModel):
    """Публичные сведения о текущем аутентифицированном пользователе.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str