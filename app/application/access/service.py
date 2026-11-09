from uuid import UUID

from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.enums import EnterpriseType, UserRole


class AccessService:
    """Проверяет права пользователя на объекты системы."""

    def __init__(
            self,
            user_repository: UserRepository,
            substation_repository: SubstationRepository,
            enterprise_repository: EnterpriseRepository,
            connection_repository: ConnectionRepository,
            urza_repository: URZARepository,
    ) -> None:
        """Сохраняет репозитории, необходимые для проверки прав доступа.

        Args:
            user_repository: Репозиторий учётных записей пользователей.
            substation_repository: Репозиторий подстанций.
            enterprise_repository: Репозиторий организационной структуры.
            connection_repository: Репозиторий присоединений.
            urza_repository: Репозиторий устройств РЗА.
        """
        self.user_repository = user_repository
        self.substation_repository = substation_repository
        self.enterprise_repository = enterprise_repository
        self.connection_repository = connection_repository
        self.urza_repository = urza_repository

    async def get_accessible_enterprise_roots(
        self,
        user_id: UUID,
    ) -> list:
        """Возвращает корневые предприятия, доступные пользователю в дереве.

        Для суперадминистратора возвращает корневые холдинги, для остальных
        ролей — назначенное предприятие, если его тип соответствует полномочиям.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Список доступных корневых предприятий. Для неактивного,
            удалённого или не найденного пользователя возвращает пустой список.
        """

        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            return []

        if not user.active or user.deleted_at is not None:
            return []

        enterprises = await self.enterprise_repository.get_all_active()

        if user.role is UserRole.SUPERADMIN:
            return [
                enterprise
                for enterprise in enterprises
                if enterprise.type is EnterpriseType.HOLDING
                and enterprise.parent_id is None
            ]

        if user.enterprise_id is None:
            return []

        user_enterprise = await self.enterprise_repository.get_by_id(
            user.enterprise_id,
        )

        if user_enterprise is None or user_enterprise.deleted_at is not None:
            return []

        if user.role is UserRole.SPECIALIST:
            if user_enterprise.type not in {
                EnterpriseType.HOLDING,
                EnterpriseType.BRANCH,
            }:
                return []

            return [user_enterprise]

        if user.role in {
            UserRole.ADMIN,
            UserRole.MANAGER,
            UserRole.ENGINEER,
        }:
            if user_enterprise.type is not EnterpriseType.DEPARTMENT:
                return []

            return [user_enterprise]

        return []

    async def can_access_enterprise(
        self,
        user_id: UUID,
        enterprise_id: UUID,
    ) -> bool:
        """Проверяет доступ пользователя к предприятию с учётом его роли.

        Суперадминистратор имеет доступ ко всем найденным предприятиям.
        Для специалиста дополнительно проверяется принадлежность предприятия
        к поддереву назначенного холдинга или филиала.

        Args:
            user_id: Идентификатор пользователя.
            enterprise_id: Идентификатор предприятия.

        Returns:
            True, если пользователь имеет доступ к предприятию, иначе False.
        """

        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            return False

        if not user.active or user.deleted_at is not None:
            return False

        enterprise = await self.enterprise_repository.get_by_id(enterprise_id)
        if enterprise is None:
            return False

        if user.role is UserRole.SUPERADMIN:
            return True

        if user.enterprise_id is None:
            return False

        if user.role in {
            UserRole.ADMIN,
            UserRole.MANAGER,
            UserRole.ENGINEER,
        }:
            return user.enterprise_id == enterprise_id

        if user.role is UserRole.SPECIALIST:
            user_enterprise = await self.enterprise_repository.get_by_id(
                user.enterprise_id
            )

            if user_enterprise is None or user_enterprise.deleted_at is not None:
                return False

            if user_enterprise.type not in {
                EnterpriseType.HOLDING,
                EnterpriseType.BRANCH,
            }:
                return False

            return await self.enterprise_repository.is_ancestor_or_same(
                ancestor_id=user.enterprise_id,
                enterprise_id=enterprise_id,
            )

        return False

    async def can_access_substation(
            self,
            user_id: UUID,
            substation_id: UUID,
    ) -> bool:
        """Проверяет доступ пользователя к подстанции через её предприятие.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            True, если подстанция найдена и пользователь имеет доступ
            к связанному с ней предприятию, иначе False.
        """

        substation = await self.substation_repository.get_by_id(substation_id)

        if substation is None:
            return False

        return await self.can_access_enterprise(
            user_id=user_id,
            enterprise_id=substation.enterprise_id,
        )

    async def can_access_connection(
            self,
            user_id: UUID,
            connection_id: UUID,
    ) -> bool:
        """Проверяет доступ пользователя к присоединению через подстанцию.

        Args:
            user_id: Идентификатор пользователя.
            connection_id: Идентификатор присоединения.

        Returns:
            True, если присоединение и его подстанция найдены, а пользователь
            имеет доступ к предприятию подстанции, иначе False.
        """

        connection = await self.connection_repository.get_by_id(connection_id)

        if connection is None:
            return False

        substation = await self.substation_repository.get_by_id(
            connection.substation_id,
        )

        if substation is None:
            return False

        return await self.can_access_enterprise(
            user_id=user_id,
            enterprise_id=substation.enterprise_id,
        )

    async def can_access_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> bool:
        """Проверяет доступ пользователя к устройству РЗА через его владельца.

        Устройство загружается вместе с возможностью проверки архивной записи;
        итоговое решение принимается по доступу пользователя к предприятию
        подстанции, к которой относится устройство.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства РЗА.

        Returns:
            True, если цепочка связей до предприятия существует и пользователь
            имеет к нему доступ, иначе False.
        """

        urza = await self.urza_repository.get_by_id_including_deleted(urza_id)

        if urza is None:
            return False

        connection = await self.connection_repository.get_by_id(
            urza.connection_id,
        )

        if connection is None:
            return False

        substation = await self.substation_repository.get_by_id(
            connection.substation_id,
        )

        if substation is None:
            return False

        return await self.can_access_enterprise(
            user_id=user_id,
            enterprise_id=substation.enterprise_id,
        )

    async def can_modify_substation(
        self, user_id: UUID, substation_id: UUID
    ) -> bool:
        """Проверяет право изменять подстанцию.

        В отличие от проверки чтения, запрещает изменение архивированной
        подстанции.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            True, если подстанция существует, не архивирована и доступна
            пользователю, иначе False.
        """
        substation = await self.substation_repository.get_by_id(substation_id)
        return bool(
            substation is not None
            and substation.deleted_at is None
            and await self.can_access_substation(user_id, substation_id)
        )

    async def can_modify_connection(
        self, user_id: UUID, connection_id: UUID
    ) -> bool:
        """Проверяет право изменять присоединение.

        Изменение запрещено, если присоединение или его подстанция архивированы.

        Args:
            user_id: Идентификатор пользователя.
            connection_id: Идентификатор присоединения.

        Returns:
            True, если присоединение и подстанция активны и пользователь имеет
            доступ к предприятию подстанции, иначе False.
        """
        connection = await self.connection_repository.get_by_id(connection_id)
        if connection is None or connection.deleted_at is not None:
            return False
        substation = await self.substation_repository.get_by_id(
            connection.substation_id
        )
        return bool(
            substation is not None
            and substation.deleted_at is None
            and await self.can_access_connection(user_id, connection_id)
        )

    async def can_modify_urza(self, user_id: UUID, urza_id: UUID) -> bool:
        """Проверяет право изменять устройство РЗА.

        Изменение запрещено, если устройство, его присоединение или подстанция
        архивированы либо отсутствует необходимая связь.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства РЗА.

        Returns:
            True, если цепочка объектов активна и пользователь имеет доступ
            к предприятию подстанции, иначе False.
        """
        urza = await self.urza_repository.get_by_id(urza_id)
        if urza is None or urza.connection is None:
            return False
        connection = urza.connection
        substation = connection.substation
        return bool(
            connection.deleted_at is None
            and substation is not None
            and substation.deleted_at is None
            and await self.can_access_urza(user_id, urza_id)
        )
