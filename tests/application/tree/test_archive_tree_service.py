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
        self.enterprise = enterprise

    async def get_all_active(self):
        return [self.enterprise]


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
        deleted_at=object(),
    )
    active_urza = SimpleNamespace(
        id=uuid4(), connection_id=connection_id, dispatch_name="Active relay",
        deleted_at=None,
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

    search_tree = await service.get_tree(
        user_id, archive_only=True, query="relay"
    )
    result_urzas = search_tree[0].substations[0].connections[0].urzas
    assert {item.id for item in result_urzas} == {active_urza.id, archived_urza.id}
    assert sum(item.is_archived for item in result_urzas) == 1
    assert len({item.id for item in result_urzas}) == 2
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
