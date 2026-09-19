
from app.application.auth.password import PasswordService
from app.application.users.repository import UserRepository
from app.domain.user import User


class InvalidCredentialsError(Exception):
    """Неверный email или пароль."""


class AuthService:
    """Аутентификация пользователей."""

    def __init__(
        self,
        user_repository: UserRepository,
        password_service: PasswordService,
    ) -> None:
        self.user_repository = user_repository
        self.password_service = password_service

    async def authenticate(
        self,
        *,
        email: str,
        password: str,
    ) -> User:
        user = await self.user_repository.get_by_email(email)

        if user is None:
            raise InvalidCredentialsError

        if user.deleted_at is not None or not user.active:
            raise InvalidCredentialsError

        if not self.password_service.verify(password, user.password_hash):
            raise InvalidCredentialsError

        return user