from uuid import UUID

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.tree.schemas import (
    ConnectionTreeNode,
    EnterpriseTreeNode,
    SubstationTreeNode,
    TreeSearchPage,
    TreeSearchResult,
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

        include_archived = archive_only
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

        if archive_only:
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

        return self._build_tree(
            root_enterprises=root_enterprises,
            enterprises=visible_enterprises,
            substations=substations,
            connections=connections,
            urzas=urzas,
        )

    async def search(
        self,
        user_id: UUID,
        query: str,
        *,
        archive_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> TreeSearchPage:
        """Search only objects included in the user's selected tree mode."""
        needle = query.strip().casefold()
        if len(needle) < 2:
            return TreeSearchPage(items=[], total=0, offset=offset, limit=limit)

        tree = await self.get_tree(user_id, archive_only=archive_only)
        results: list[TreeSearchResult] = []
        type_order = {"enterprise": 0, "substation": 1, "connection": 2, "urza": 3}

        def add_match(
            *, object_id: UUID, object_type: str, type_label: str, name: str,
            path: list[str], path_ids: list[UUID], fields: list[tuple[str, str]],
            archived: bool = False, has_card: bool = False,
        ) -> None:
            candidates = []
            field_priority = {
                "Полное наименование": 0, "Краткое наименование": 1,
                "Диспетчерское имя": 0, "Инвентарный номер": 1,
            }
            for field_name, value in fields:
                folded = value.casefold()
                if needle in folded:
                    rank = 0 if folded == needle else 1 if folded.startswith(needle) else 2
                    candidates.append((rank, field_priority[field_name], field_name, value))
            if not candidates:
                return
            rank, _priority, field_name, value = min(candidates)
            results.append(TreeSearchResult(
                id=object_id, object_type=object_type, type_label=type_label,
                name=name, matched_field=field_name, matched_value=value,
                path=path, path_ids=path_ids, archived=archived, relevance=rank,
                has_card=has_card,
            ))

        def visit_enterprise(
            node: EnterpriseTreeNode, ancestors: list[str], ancestor_ids: list[UUID]
        ) -> None:
            own_path = [*ancestors, node.full_name]
            own_path_ids = [*ancestor_ids, node.id]
            if not archive_only:
                add_match(
                    object_id=node.id, object_type="enterprise", type_label={
                        "holding": "Холдинг", "branch": "Филиал",
                        "department": "Производственное подразделение",
                    }.get(node.type, "Предприятие"), name=node.full_name,
                    path=own_path,
                    path_ids=own_path_ids,
                    fields=[("Полное наименование", node.full_name), ("Краткое наименование", node.short_name)],
                    has_card=node.type == "department",
                )
            for station in node.substations:
                station_path = [*own_path, station.dispatch_name]
                if not archive_only or station.is_archived:
                    add_match(
                        object_id=station.id, object_type="substation", type_label="Подстанция",
                        name=station.dispatch_name, path=station_path,
                        path_ids=[*own_path_ids, station.id],
                        fields=[("Диспетчерское имя", station.dispatch_name)], archived=station.is_archived,
                    )
                for connection in station.connections:
                    connection_path = [*station_path, connection.dispatch_name]
                    if not archive_only or connection.is_archived:
                        add_match(
                            object_id=connection.id, object_type="connection", type_label="Присоединение",
                            name=connection.dispatch_name, path=connection_path,
                            path_ids=[*own_path_ids, station.id, connection.id],
                            fields=[("Диспетчерское имя", connection.dispatch_name)], archived=connection.is_archived,
                        )
                    for urza in connection.urzas:
                        if archive_only and not urza.is_archived:
                            continue
                        add_match(
                            object_id=urza.id, object_type="urza", type_label="УРЗА",
                            name=urza.dispatch_name, path=[*connection_path, urza.dispatch_name],
                            path_ids=[*own_path_ids, station.id, connection.id, urza.id],
                            fields=[("Диспетчерское имя", urza.dispatch_name), ("Инвентарный номер", urza.inventory_number or "")],
                            archived=urza.is_archived,
                        )
            for child in node.children:
                visit_enterprise(child, own_path, own_path_ids)

        for enterprise in tree:
            visit_enterprise(enterprise, [], [])

        results.sort(key=lambda item: (
            type_order[item.object_type], item.relevance, item.name.casefold(), str(item.id),
        ))
        return TreeSearchPage(
            items=results[offset:offset + limit], total=len(results), offset=offset, limit=limit,
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
                    inventory_number=getattr(urza, "inventory_number", None),
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
