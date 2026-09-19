from uuid import UUID

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.tree.schemas import (
    ConnectionTreeNode,
    EnterpriseTreeNode,
    SubstationTreeNode,
    URZATreeNode,
)
from app.application.urzas.repository import URZARepository
from app.domain.enums import EnterpriseType


class TreeService:
    """Формирует дерево объектов РЗА для пользователя."""

    def __init__(
        self,
        *,
        enterprise_repository: EnterpriseRepository,
        substation_repository: SubstationRepository,
        connection_repository: ConnectionRepository,
        urza_repository: URZARepository,
        access_service: AccessService,
    ) -> None:
        self.enterprise_repository = enterprise_repository
        self.substation_repository = substation_repository
        self.connection_repository = connection_repository
        self.urza_repository = urza_repository
        self.access_service = access_service

    async def get_tree(
        self,
        user_id: UUID,
    ) -> list[EnterpriseTreeNode]:
        """Возвращает дерево объектов, доступных пользователю."""

        root_enterprises = (
            await self.access_service.get_accessible_enterprise_roots(
                user_id,
            )
        )

        if not root_enterprises:
            return []

        all_enterprises = await self.enterprise_repository.get_all_active()

        visible_enterprise_ids = self._collect_enterprise_ids(
            root_enterprises=root_enterprises,
            enterprises=all_enterprises,
        )

        visible_enterprises = [
            enterprise
            for enterprise in all_enterprises
            if enterprise.id in visible_enterprise_ids
        ]

        substations = await self.substation_repository.get_by_enterprise_ids(
            visible_enterprise_ids,
        )

        substation_ids = {
            substation.id
            for substation in substations
        }

        connections = await self.connection_repository.get_by_substation_ids(
            substation_ids,
        )

        connection_ids = {
            connection.id
            for connection in connections
        }

        urzas = await self.urza_repository.get_by_connection_ids(
            connection_ids,
        )

        return self._build_tree(
            root_enterprises=root_enterprises,
            enterprises=visible_enterprises,
            substations=substations,
            connections=connections,
            urzas=urzas,
        )

    @staticmethod
    def _collect_enterprise_ids(
        *,
        root_enterprises,
        enterprises,
    ) -> set[UUID]:
        """Собирает корневые предприятия и всех их потомков."""

        enterprises_by_parent: dict[
            UUID | None,
            list,
        ] = {}

        for enterprise in enterprises:
            enterprises_by_parent.setdefault(
                enterprise.parent_id,
                [],
            ).append(enterprise)

        result: set[UUID] = set()

        def collect(enterprise_id: UUID) -> None:
            if enterprise_id in result:
                return

            result.add(enterprise_id)

            for child in enterprises_by_parent.get(
                enterprise_id,
                [],
            ):
                collect(child.id)

        for root in root_enterprises:
            collect(root.id)

        return result

    @staticmethod
    def _build_tree(
        *,
        root_enterprises,
        enterprises,
        substations,
        connections,
        urzas,
    ) -> list[EnterpriseTreeNode]:
        """Преобразует плоские записи БД в дерево DTO."""

        urzas_by_connection: dict[
            UUID,
            list[URZATreeNode],
        ] = {}

        for urza in urzas:
            urzas_by_connection.setdefault(
                urza.connection_id,
                [],
            ).append(
                URZATreeNode(
                    id=urza.id,
                    dispatch_name=urza.dispatch_name,
                ),
            )

        connections_by_substation: dict[
            UUID,
            list[ConnectionTreeNode],
        ] = {}

        for connection in connections:
            connections_by_substation.setdefault(
                connection.substation_id,
                [],
            ).append(
                ConnectionTreeNode(
                    id=connection.id,
                    dispatch_name=connection.dispatch_name,
                    urzas=sorted(
                        urzas_by_connection.get(
                            connection.id,
                            [],
                        ),
                        key=lambda item: item.dispatch_name,
                    ),
                ),
            )

        substations_by_enterprise: dict[
            UUID,
            list[SubstationTreeNode],
        ] = {}

        for substation in substations:
            substations_by_enterprise.setdefault(
                substation.enterprise_id,
                [],
            ).append(
                SubstationTreeNode(
                    id=substation.id,
                    dispatch_name=substation.dispatch_name,
                    connections=sorted(
                        connections_by_substation.get(
                            substation.id,
                            [],
                        ),
                        key=lambda item: item.dispatch_name,
                    ),
                ),
            )

        enterprises_by_parent: dict[
            UUID | None,
            list,
        ] = {}

        for enterprise in enterprises:
            enterprises_by_parent.setdefault(
                enterprise.parent_id,
                [],
            ).append(enterprise)

        def build_enterprise(
            enterprise,
        ) -> EnterpriseTreeNode:
            children = sorted(
                enterprises_by_parent.get(
                    enterprise.id,
                    [],
                ),
                key=lambda item: item.full_name,
            )

            return EnterpriseTreeNode(
                id=enterprise.id,
                type=enterprise.type.value,
                full_name=enterprise.full_name,
                short_name=enterprise.short_name,
                children=[
                    build_enterprise(child)
                    for child in children
                ],
                substations=sorted(
                    substations_by_enterprise.get(
                        enterprise.id,
                        [],
                    ),
                    key=lambda item: item.dispatch_name,
                ),
            )

        return [
            build_enterprise(root)
            for root in sorted(
                root_enterprises,
                key=lambda item: item.full_name,
            )
            if root.type in {
                EnterpriseType.HOLDING,
                EnterpriseType.BRANCH,
                EnterpriseType.DEPARTMENT,
            }
        ]