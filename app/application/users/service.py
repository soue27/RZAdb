import re
from datetime import UTC, datetime
from uuid import UUID

from app.application.auth.password import PasswordService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.users.repository import UserRepository
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User


class UserOperationError(Exception):
    """Операция с пользователем отклонена правилами доступа или предметной области."""


class UserService:
    """Выполняет административные операции с учётными записями пользователей."""

    def __init__(
        self,
        repository: UserRepository,
        enterprise_repository: EnterpriseRepository,
        password_service: PasswordService,
    ) -> None:
        """Сохраняет репозитории и сервис хеширования паролей.

        Args:
            repository: Репозиторий пользователей.
            enterprise_repository: Репозиторий для проверки предприятия.
            password_service: Сервис создания и проверки хешей паролей.
        """
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
        """Создаёт учётную запись и помечает временный пароль для смены.

        Операция доступна только суперадминистратору. Email проверяется на
        уникальность, а пароль сохраняется только в виде хеша.

        Args:
            actor: Пользователь, выполняющий операцию.
            full_name: ФИО нового пользователя.
            email: Email новой учётной записи.
            role: Системная роль пользователя.
            enterprise_id: Предприятие пользователя или None.
            access_category: Категория допуска к работам.
            temporary_password: Временный пароль для первого входа.

        Returns:
            Созданная учётная запись.

        Raises:
            UserOperationError: Если у инициатора недостаточно прав,
                поля некорректны, предприятие не найдено или email занят.
        """
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
        """Изменяет основные сведения и область ответственности пользователя.

        Изменять собственную учётную запись через эту операцию запрещено.

        Args:
            actor: Суперадминистратор, выполняющий изменение.
            user_id: Идентификатор изменяемого пользователя.
            full_name: Новое ФИО.
            email: Новый email.
            role: Новая системная роль.
            enterprise_id: Новое предприятие или None.
            access_category: Новая категория допуска.

        Returns:
            Обновлённая учётная запись.

        Raises:
            UserOperationError: При недостатке прав, попытке изменить себя,
                отсутствии пользователя/предприятия, некорректных данных
                или занятом email.
        """
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
        """Устанавливает пользователю временный пароль с обязательной сменой.

        Суперадминистратор не может сбросить пароль собственной учётной записи.

        Args:
            actor: Суперадминистратор, выполняющий сброс.
            user_id: Идентификатор пользователя.
            temporary_password: Новый временный пароль.

        Returns:
            Обновлённая учётная запись.

        Raises:
            UserOperationError: При недостатке прав, попытке сбросить свой
                пароль, отсутствии пользователя или некорректном пароле.
        """
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
        """Включает или отключает учётную запись пользователя.

        Нельзя отключить собственную учётную запись через административную
        операцию.

        Args:
            actor: Суперадминистратор, выполняющий операцию.
            user_id: Идентификатор пользователя.
            active: Новое состояние активности.

        Returns:
            Обновлённая учётная запись.

        Raises:
            UserOperationError: При недостатке прав, попытке изменить себя
                или отсутствии пользователя.
        """
        self._require_superadmin(actor)
        if user_id == actor.id:
            raise UserOperationError("Нельзя отключить собственную учётную запись.")
        user = await self._get_manageable(user_id)
        user.active = active
        user.updated_by = actor.id
        await self.repository.flush()
        return user

    async def archive(self, *, actor: User, user_id: UUID) -> User:
        """Архивирует учётную запись без физического удаления.

        Сохраняет время и инициатора архивирования. Архивировать самого себя
        через эту операцию нельзя.

        Args:
            actor: Суперадминистратор, выполняющий архивирование.
            user_id: Идентификатор пользователя.

        Returns:
            Архивированная учётная запись.

        Raises:
            UserOperationError: При недостатке прав, попытке архивировать себя
                или отсутствии пользователя.
        """
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
        """Изменяет пароль текущего пользователя.

        При первом входе допускается смена временного пароля без проверки
        старого; в остальных случаях требуется корректный текущий пароль.
        Новый пароль должен содержать не менее 12 символов и отличаться
        от сохранённого.

        Args:
            user: Учётная запись, пароль которой изменяется.
            current_password: Текущий пароль или None при обязательной
                первоначальной смене.
            new_password: Новый пароль.

        Raises:
            UserOperationError: Если новый пароль слишком короткий, текущий
                пароль неверен или новый пароль совпадает с текущим.
        """
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
