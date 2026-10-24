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
        *,
        archive_only: bool = False,
        query: str | None = None,
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

        has_query = bool(query and query.strip())
        include_archived = has_query or archive_only
        substations = await self.substation_repository.get_by_enterprise_ids(
            visible_enterprise_ids,
            include_archived=include_archived,
        )

        substation_ids = {
            substation.id
            for substation in substations
        }

        connections = await self.connection_repository.get_by_substation_ids(
            substation_ids,
            include_archived=include_archived,
        )

        connection_ids = {
            connection.id
            for connection in connections
        }

        urzas = await self.urza_repository.get_by_connection_ids(
            connection_ids,
            include_archived=include_archived,
        )

        if archive_only and not has_query:
            urzas = [item for item in urzas if item.deleted_at is not None]
            archived_urza_connection_ids = {
                item.connection_id for item in urzas if item.deleted_at is not None
            }
            connections = [
                item for item in connections
                if item.deleted_at is not None or item.id in archived_urza_connection_ids
            ]
            archived_connection_substation_ids = {
                item.substation_id for item in connections if item.deleted_at is not None
            }
            substations = [
                item for item in substations
                if item.deleted_at is not None
                or item.id in archived_connection_substation_ids
                or any(
                    connection.substation_id == item.id
                    and connection.id in archived_urza_connection_ids
                    for connection in connections
                )
            ]

        if query and query.strip():
            needle = query.strip().casefold()
            matched_urza_ids = {
                item.id for item in urzas if needle in item.dispatch_name.casefold()
            }
            matched_connection_ids = {
                item.id for item in connections if needle in item.dispatch_name.casefold()
            }
            matched_substation_ids = {
                item.id for item in substations
                if needle in item.dispatch_name.casefold()
            }
            substation_by_connection = {
                item.id: item.substation_id for item in connections
            }
            connection_ids_by_substation: dict[UUID, set[UUID]] = {}
            urza_connection_ids_by_id = {}
            for item in connections:
                connection_ids_by_substation.setdefault(
                    item.substation_id, set()
                ).add(item.id)
            for item in urzas:
                urza_connection_ids_by_id[item.id] = item.connection_id
            matched_urza_connection_ids = {
                urza_connection_ids_by_id[item_id]
                for item_id in matched_urza_ids
            }
            relevant_connection_ids = (
                matched_connection_ids
                | matched_urza_connection_ids
                | set().union(*(
                    connection_ids_by_substation.get(item_id, set())
                    for item_id in matched_substation_ids
                ))
            )
            relevant_substation_ids = matched_substation_ids | {
                substation_by_connection[item_id]
                for item_id in relevant_connection_ids
            }
            connections = [
                item for item in connections if item.id in relevant_connection_ids
            ]
            urzas = [
                item for item in urzas
                if item.id in matched_urza_ids
                or item.connection_id in matched_connection_ids
                or substation_by_connection.get(item.connection_id)
                in matched_substation_ids
            ]
            substations = [
                item for item in substations if item.id in relevant_substation_ids
            ]

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
                    is_archived=urza.deleted_at is not None,
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
                    is_archived=connection.deleted_at is not None,
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
                    is_archived=substation.deleted_at is not None,
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
