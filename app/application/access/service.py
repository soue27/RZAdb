from uuid import UUID

from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.users.repository import UserRepository
from app.application.connections.repository import ConnectionRepository
from app.domain.enums import EnterpriseType, UserRole


class AccessService:
    """Проверяет права пользователя на объекты системы."""

    def __init__(
            self,
            user_repository: UserRepository,
            substation_repository: SubstationRepository,
            enterprise_repository: EnterpriseRepository,
            connection_repository: ConnectionRepository,
    ) -> None:
        self.user_repository = user_repository
        self.substation_repository = substation_repository
        self.enterprise_repository = enterprise_repository
        self.connection_repository = connection_repository

    async def can_access_enterprise(
        self,
        user_id: UUID,
        enterprise_id: UUID,
    ) -> bool:
        """Проверяет доступ пользователя к предприятию."""

        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            return False

        if not user.active or user.deleted_at is not None:
            return False

        enterprise = await self.enterprise_repository.get_by_id(enterprise_id)
        if enterprise is None or enterprise.deleted_at is not None:
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
        """Проверяет доступ пользователя к подстанции."""

        substation = await self.substation_repository.get_by_id(substation_id)

        if substation is None:
            return False

        if substation.deleted_at is not None:
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
        """Проверяет доступ пользователя к присоединению."""

        connection = await self.connection_repository.get_by_id(connection_id)

        if connection is None:
            return False

        if connection.deleted_at is not None:
            return False

        substation = await self.substation_repository.get_by_id(
            connection.substation_id,
        )

        if substation is None:
            return False

        if substation.deleted_at is not None:
            return False

        return await self.can_access_enterprise(
            user_id=user_id,
            enterprise_id=substation.enterprise_id,
        )