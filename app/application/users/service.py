import re
from datetime import UTC, datetime
from uuid import UUID

from app.application.auth.password import PasswordService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.users.repository import UserRepository
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User


class UserOperationError(Exception):
    """User operation rejected by domain or access rules."""


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        enterprise_repository: EnterpriseRepository,
        password_service: PasswordService,
    ) -> None:
        self.repository = repository
        self.enterprise_repository = enterprise_repository
        self.password_service = password_service

    async def create(
        self,
        *,
        actor: User,
        full_name: str,
        email: str,
        role: UserRole,
        enterprise_id: UUID | None,
        access_category: AccessCategory,
        temporary_password: str,
    ) -> User:
        self._require_superadmin(actor)
        full_name = full_name.strip()
        email = email.strip()
        self._validate_fields(full_name, email, temporary_password)
        await self._validate_enterprise(enterprise_id)
        if await self.repository.get_by_email(email) is not None:
            raise UserOperationError("Пользователь с таким Email уже существует.")

        user = User(
            full_name=full_name,
            email=email,
            role=role,
            enterprise_id=enterprise_id,
            access_category=access_category,
            password_hash=self.password_service.hash(temporary_password),
            must_change_password=True,
            active=True,
            created_by=actor.id,
            updated_by=actor.id,
        )
        return await self.repository.add(user)

    async def update(
        self,
        *,
        actor: User,
        user_id: UUID,
        full_name: str,
        email: str,
        role: UserRole,
        enterprise_id: UUID | None,
        access_category: AccessCategory,
    ) -> User:
        self._require_superadmin(actor)
        if user_id == actor.id:
            raise UserOperationError("Нельзя изменять собственную учётную запись.")
        user = await self._get_manageable(user_id)
        full_name = full_name.strip()
        email = email.strip()
        self._validate_fields(full_name, email)
        await self._validate_enterprise(enterprise_id)
        duplicate = await self.repository.get_by_email(email)
        if duplicate is not None and duplicate.id != user.id:
            raise UserOperationError("Пользователь с таким Email уже существует.")

        user.full_name = full_name
        user.email = email
        user.role = role
        user.enterprise_id = enterprise_id
        user.access_category = access_category
        user.updated_by = actor.id
        await self.repository.flush()
        return user

    async def reset_password(
        self, *, actor: User, user_id: UUID, temporary_password: str
    ) -> User:
        self._require_superadmin(actor)
        if user_id == actor.id:
            raise UserOperationError("Нельзя сбросить собственный пароль через админку.")
        user = await self._get_manageable(user_id)
        self._validate_password(temporary_password)
        user.password_hash = self.password_service.hash(temporary_password)
        user.must_change_password = True
        user.updated_by = actor.id
        await self.repository.flush()
        return user

    async def set_active(self, *, actor: User, user_id: UUID, active: bool) -> User:
        self._require_superadmin(actor)
        if user_id == actor.id:
            raise UserOperationError("Нельзя отключить собственную учётную запись.")
        user = await self._get_manageable(user_id)
        user.active = active
        user.updated_by = actor.id
        await self.repository.flush()
        return user

    async def archive(self, *, actor: User, user_id: UUID) -> User:
        self._require_superadmin(actor)
        if user_id == actor.id:
            raise UserOperationError("Нельзя архивировать собственную учётную запись.")
        user = await self._get_manageable(user_id)
        user.deleted_at = datetime.now(UTC)
        user.deleted_by = actor.id
        user.updated_by = actor.id
        await self.repository.flush()
        return user

    async def change_password(
        self,
        *,
        user: User,
        current_password: str | None,
        new_password: str,
    ) -> None:
        if len(new_password) < 12:
            raise UserOperationError("Пароль должен содержать не менее 12 символов.")
        if not user.must_change_password and (
            current_password is None
            or not self.password_service.verify(current_password, user.password_hash)
        ):
            raise UserOperationError("Текущий пароль указан неверно.")
        if self.password_service.verify(new_password, user.password_hash):
            raise UserOperationError("Новый пароль должен отличаться от текущего.")
        user.password_hash = self.password_service.hash(new_password)
        user.must_change_password = False
        user.updated_by = user.id
        await self.repository.flush()

    async def _get_manageable(self, user_id: UUID) -> User:
        user = await self.repository.get_managed_by_id(user_id)
        if user is None:
            raise UserOperationError("Пользователь не найден.")
        return user

    async def _validate_enterprise(self, enterprise_id: UUID | None) -> None:
        if enterprise_id is not None and await self.enterprise_repository.get_by_id(
            enterprise_id
        ) is None:
            raise UserOperationError("Предприятие не найдено.")

    @staticmethod
    def _validate_fields(full_name: str, email: str, password: str | None = None) -> None:
        if not full_name.strip():
            raise UserOperationError("Укажите ФИО.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 255:
            raise UserOperationError("Укажите корректный Email.")

        if password is not None:
            UserService._validate_password(password)

    @staticmethod
    def _validate_password(password: str) -> None:
        if not password:
            raise UserOperationError("Пароль не должен быть пустым.")

    @staticmethod
    def _require_superadmin(actor: User) -> None:
        if actor.role is not UserRole.SUPERADMIN:
            raise UserOperationError("Недостаточно прав.")
