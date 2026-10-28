from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.tree.service import TreeService
from app.domain.enums import EnterpriseType


class _Access:
    def __init__(self, root):
        self.root = root

    async def get_accessible_enterprise_roots(self, _user_id):
        return [self.root]


class _Enterprises:
    def __init__(self, enterprise):
        self.enterprises = enterprise if isinstance(enterprise, list) else [enterprise]

    async def get_all_active(self):
        return self.enterprises


class _Objects:
    def __init__(self, items):
        self.items = items
        self.include_archived = None

    async def get_by_enterprise_ids(self, _ids, *, include_archived=False):
        self.include_archived = include_archived
        return [item for item in self.items if include_archived or item.deleted_at is None]

    async def get_by_substation_ids(self, _ids, *, include_archived=False):
        self.include_archived = include_archived
        return [item for item in self.items if include_archived or item.deleted_at is None]

    async def get_by_connection_ids(self, _ids, *, include_archived=False):
        self.include_archived = include_archived
        return [item for item in self.items if include_archived or item.deleted_at is None]


@pytest.mark.asyncio
async def test_tree_search_defaults_to_active_and_including_archive_is_scoped():
    user_id = uuid4()
    enterprise = SimpleNamespace(
        id=uuid4(), parent_id=None, type=EnterpriseType.DEPARTMENT,
        full_name="Dept", short_name="Dept",
    )
    root = enterprise
    station_id, connection_id = uuid4(), uuid4()
    active_station = SimpleNamespace(
        id=station_id, enterprise_id=enterprise.id, dispatch_name="Active station",
        deleted_at=None,
    )
    archived_station = SimpleNamespace(
        id=uuid4(), enterprise_id=enterprise.id, dispatch_name="Archive station",
        deleted_at=object(),
    )
    active_connection = SimpleNamespace(
        id=connection_id, substation_id=station_id, dispatch_name="Active line",
        deleted_at=None,
    )
    archived_urza = SimpleNamespace(
        id=uuid4(), connection_id=connection_id, dispatch_name="Archive relay",
        inventory_number="INV-ARCHIVE", deleted_at=object(),
    )
    active_urza = SimpleNamespace(
        id=uuid4(), connection_id=connection_id, dispatch_name="Active relay",
        inventory_number="INV-ACTIVE", deleted_at=None,
    )
    substations = _Objects([active_station, archived_station])
    connections = _Objects([active_connection])
    urzas = _Objects([active_urza, archived_urza])
    service = TreeService(
        enterprise_repository=_Enterprises(enterprise),
        substation_repository=substations,
        connection_repository=connections,
        urza_repository=urzas,
        access_service=_Access(root),
    )

    active_tree = await service.get_tree(user_id)
    assert [item.dispatch_name for item in active_tree[0].substations] == ["Active station"]
    assert not substations.include_archived

    search_tree = await service.get_tree(user_id, archive_only=True, query="relay")
    result_urzas = search_tree[0].substations[0].connections[0].urzas
    assert [item.id for item in result_urzas] == [archived_urza.id]
    assert substations.include_archived
    assert connections.include_archived
    assert urzas.include_archived

    archive_tree = await service.get_tree(user_id, archive_only=True)
    assert len(archive_tree[0].substations) == 2
    archived_results = [
        urza
        for station in archive_tree[0].substations
        for connection in station.connections
        for urza in connection.urzas
    ]
    assert len(archived_results) == 1
    assert archived_results[0].is_archived

    active_page = await service.search(user_id, "relay")
    assert [item.id for item in active_page.items] == [active_urza.id]
    assert active_page.items[0].matched_field == "Диспетчерское имя"
    assert active_page.items[0].relevance == 2
    all_active_matches = await service.search(user_id, "active")
    assert [item.object_type for item in all_active_matches.items] == [
        "substation", "connection", "urza",
    ]
    assert len({item.id for item in all_active_matches.items}) == 3
    assert all_active_matches.items[-1].matched_field == "Диспетчерское имя"
    inventory_page = await service.search(user_id, "inv-act")
    assert [item.id for item in inventory_page.items] == [active_urza.id]
    assert inventory_page.items[0].matched_field == "Инвентарный номер"
    archived_page = await service.search(user_id, "relay", archive_only=True)
    assert [item.id for item in archived_page.items] == [archived_urza.id]


@pytest.mark.asyncio
async def test_search_ranks_enterprise_fields_and_paginates_deterministically():
    enterprise = SimpleNamespace(
        id=uuid4(), parent_id=None, type=EnterpriseType.DEPARTMENT,
        full_name="North Relay Department", short_name="Relay", deleted_at=None,
    )
    child = SimpleNamespace(
        id=uuid4(), parent_id=enterprise.id, type=EnterpriseType.DEPARTMENT,
        full_name="Relay Branch", short_name="RB", deleted_at=None,
    )
    service = TreeService(
        enterprise_repository=_Enterprises([enterprise, child]),
        substation_repository=_Objects([]), connection_repository=_Objects([]),
        urza_repository=_Objects([]), access_service=_Access(enterprise),
    )
    exact = await service.search(uuid4(), "relay", limit=1)
    assert exact.total == 2
    assert exact.items[0].id == enterprise.id
    assert exact.items[0].matched_field == "Краткое наименование"
    assert exact.items[0].relevance == 0
    assert exact.items[0].has_card
    next_page = await service.search(uuid4(), "relay", offset=1, limit=1)
    assert [item.id for item in next_page.items] == [child.id]
    assert next_page.items[0].relevance == 1
    empty = await service.search(uuid4(), "r")
    assert empty.total == 0
