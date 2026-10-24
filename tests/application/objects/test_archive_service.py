from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.objects.archive_service import (
    ArchiveBlockedError,
    ArchiveService,
)
from app.application.objects.exceptions import ObjectAccessDeniedError
from app.domain.enums import ArchiveEventType, TaskStatus, UserRole


def _owner(**values):
    return SimpleNamespace(id=uuid4(), deleted_at=None, deleted_by=None, **values)


class FakeArchiveRepository:
    def __init__(self, objects=(), connections=(), urzas=(), blockers=()):
        self.objects = {(kind, item.id): item for kind, item in objects}
        self.connections = list(connections)
        self.urzas = list(urzas)
        self.blockers = list(blockers)
        self.lock_calls = []
        self.events = []

    async def get_object(self, kind, object_id):
        return self.objects.get((kind, object_id))

    async def lock_object(self, kind, object_id):
        self.lock_calls.append((kind, object_id))
        return await self.get_object(kind, object_id)

    async def get_active_connections(self, substation_id):
        return sorted(
            [
                item
                for item in self.connections
                if item.substation_id == substation_id and item.deleted_at is None
            ],
            key=lambda item: item.id,
        )

    async def get_active_urzas(self, connection_ids):
        return sorted(
            [
                item
                for item in self.urzas
                if item.connection_id in connection_ids and item.deleted_at is None
            ],
            key=lambda item: item.id,
        )

    async def get_blocking_processes(self, **kwargs):
        return list(self.blockers)

    async def add_events(self, events):
        self.events.extend(events)

    async def get_history(self, kind, object_id):
        return [
            event for event in self.events if getattr(event, f"{kind}_id") == object_id
        ]


def _service(repository, *, role=UserRole.MANAGER, allowed=True):
    access = SimpleNamespace(
        user_repository=SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(role=role))
        ),
        substation_repository=SimpleNamespace(),
        enterprise_repository=SimpleNamespace(),
        connection_repository=SimpleNamespace(),
        urza_repository=SimpleNamespace(),
        can_access_substation=AsyncMock(return_value=allowed),
        can_access_connection=AsyncMock(return_value=allowed),
        can_access_urza=AsyncMock(return_value=allowed),
    )
    return ArchiveService(repository, access), access


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
async def test_archive_cascades_active_branch_and_uses_one_operation_id(kind):
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    archived_connection = _owner(substation_id=station.id)
    archived_connection.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    archived_connection.deleted_by = uuid4()
    archived_urza = _owner(connection_id=connection.id)
    archived_urza.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    archived_urza.deleted_by = uuid4()
    prior_event = SimpleNamespace(connection_id=archived_connection.id)
    objects = [("substation", station), ("connection", connection), ("urza", urza)]
    repo = FakeArchiveRepository(
        objects,
        connections=[connection, archived_connection],
        urzas=[urza, archived_urza],
    )
    repo.events.append(prior_event)
    service, _ = _service(repo)
    target = {"substation": station, "connection": connection, "urza": urza}[kind]
    operation_at = datetime(2026, 10, 24, tzinfo=UTC)
    actor_id = uuid4()

    result = await service.archive(
        actor_id=actor_id,
        object_type=kind,
        object_id=target.id,
        reason="  Плановая замена  ",
        occurred_at=operation_at,
    )

    assert result.object_ids == tuple(
        (event_kind, event_id)
        for event_kind, event_id in (
            [
                ("substation", station.id),
                ("connection", connection.id),
                ("urza", urza.id),
            ]
            if kind == "substation"
            else [("connection", connection.id), ("urza", urza.id)]
            if kind == "connection"
            else [("urza", urza.id)]
        )
    )
    operation_events = repo.events[1:]
    assert len(operation_events) == len(result.object_ids)
    assert len({event.operation_id for event in operation_events}) == 1
    assert all(
        event.event_type is ArchiveEventType.ARCHIVED for event in operation_events
    )
    assert all(event.reason == "Плановая замена" for event in operation_events)
    assert all(event.occurred_at == operation_at for event in operation_events)
    changed_items = {
        "substation": station,
        "connection": connection,
        "urza": urza,
    }
    assert all(
        changed_items[event_kind].deleted_by == actor_id
        for event_kind, _ in result.object_ids
    )
    assert archived_connection.deleted_at.year == 2025
    assert archived_connection.deleted_by is not None
    assert archived_urza.deleted_by is not None
    assert repo.events[0] is prior_event


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "  \n  ", "x" * 2001])
async def test_archive_rejects_invalid_reason_without_mutation(reason):
    station = _owner()
    repo = FakeArchiveRepository([("substation", station)])
    service, _ = _service(repo)

    with pytest.raises(ValueError):
        await service.archive(
            actor_id=uuid4(),
            object_type="substation",
            object_id=station.id,
            reason=reason,
        )

    assert station.deleted_at is None
    assert repo.events == []


@pytest.mark.asyncio
async def test_archive_accepts_reason_of_2000_characters_after_trim():
    station = _owner()
    repo = FakeArchiveRepository([("substation", station)])
    service, _ = _service(repo)

    await service.archive(
        actor_id=uuid4(),
        object_type="substation",
        object_id=station.id,
        reason=f"  {'x' * 2000}  ",
    )

    assert len(repo.events[0].reason) == 2000


@pytest.mark.asyncio
async def test_blockers_abort_without_mutating_or_creating_events():
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    repo = FakeArchiveRepository(
        [("substation", station), ("connection", connection), ("urza", urza)],
        connections=[connection],
        urzas=[urza],
        blockers=[("task", uuid4(), TaskStatus.COMPLETED)],
    )
    service, _ = _service(repo)

    with pytest.raises(ArchiveBlockedError) as error:
        await service.archive(
            actor_id=uuid4(),
            object_type="substation",
            object_id=station.id,
            reason="Причина",
        )

    assert error.value.blockers[0].status is TaskStatus.COMPLETED
    assert all(item.deleted_at is None for item in (station, connection, urza))
    assert repo.events == []


@pytest.mark.asyncio
async def test_archiving_already_archived_object_is_noop():
    archived_at = datetime(2025, 1, 1, tzinfo=UTC)
    station = _owner()
    station.deleted_at = archived_at
    station.deleted_by = uuid4()
    repo = FakeArchiveRepository([("substation", station)])
    service, _ = _service(repo)

    await service.archive(
        actor_id=uuid4(),
        object_type="substation",
        object_id=station.id,
        reason="Повтор",
    )

    assert station.deleted_at == archived_at
    assert repo.events == []


@pytest.mark.asyncio
async def test_preview_is_read_only_and_archive_preserves_document_and_file_links():
    station = _owner()
    connection = _owner(substation_id=station.id)
    document_link = object()
    file_link = object()
    urza = _owner(connection_id=connection.id)
    urza.document_link = document_link
    urza.file_link = file_link
    repo = FakeArchiveRepository(
        [("substation", station), ("connection", connection), ("urza", urza)],
        connections=[connection],
        urzas=[urza],
    )
    service, _ = _service(repo)

    preview = await service.preview(
        actor_id=uuid4(), object_type="substation", object_id=station.id
    )
    assert len(preview.object_ids) == 3
    assert all(item.deleted_at is None for item in (station, connection, urza))
    assert repo.events == []

    await service.archive(
        actor_id=uuid4(),
        object_type="substation",
        object_id=station.id,
        reason="Причина",
    )
    assert urza.document_link is document_link
    assert urza.file_link is file_link


@pytest.mark.asyncio
async def test_restore_only_target_and_writes_event():
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    connection.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    urza.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    repo = FakeArchiveRepository(
        [("substation", station), ("connection", connection), ("urza", urza)]
    )
    service, _ = _service(repo)

    event = await service.restore(
        actor_id=uuid4(),
        object_type="connection",
        object_id=connection.id,
        reason="  Исправление  ",
    )

    assert connection.deleted_at is None
    assert connection.deleted_by is None
    assert urza.deleted_at is not None
    assert event.event_type is ArchiveEventType.RESTORED
    assert event.reason == "Исправление"
    assert event.connection_id == connection.id


@pytest.mark.asyncio
async def test_restore_rejects_archived_parent_and_active_restore_is_noop():
    station = _owner()
    connection = _owner(substation_id=station.id)
    connection.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    station.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    repo = FakeArchiveRepository([("substation", station), ("connection", connection)])
    service, _ = _service(repo)

    with pytest.raises(ValueError, match="архивной подстанции"):
        await service.restore(
            actor_id=uuid4(), object_type="connection", object_id=connection.id
        )
    assert connection.deleted_at is not None
    assert repo.events == []

    station.deleted_at = None
    connection.deleted_at = None
    assert (
        await service.restore(
            actor_id=uuid4(), object_type="connection", object_id=connection.id
        )
        is None
    )
    assert repo.events == []


@pytest.mark.asyncio
async def test_restore_urza_rejects_archived_connection():
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    connection.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    urza.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    repo = FakeArchiveRepository(
        [("substation", station), ("connection", connection), ("urza", urza)]
    )
    service, _ = _service(repo)

    with pytest.raises(ValueError, match="архивного присоединения"):
        await service.restore(actor_id=uuid4(), object_type="urza", object_id=urza.id)
    assert urza.deleted_at is not None
    assert repo.events == []


@pytest.mark.asyncio
async def test_disallowed_role_or_out_of_scope_access_is_rejected():
    station = _owner()
    repo = FakeArchiveRepository([("substation", station)])
    service, _ = _service(repo, role=UserRole.ENGINEER)

    with pytest.raises(ObjectAccessDeniedError):
        await service.get_history(
            actor_id=uuid4(), object_type="substation", object_id=station.id
        )

    service, _ = _service(repo, allowed=False)
    with pytest.raises(ObjectAccessDeniedError):
        await service.archive(
            actor_id=uuid4(),
            object_type="substation",
            object_id=station.id,
            reason="Причина",
        )
    assert repo.events == []


@pytest.mark.asyncio
async def test_lock_order_follows_parent_then_children():
    station = _owner()
    connection_b = _owner(substation_id=station.id)
    connection_a = _owner(substation_id=station.id)
    urza_b = _owner(connection_id=connection_b.id)
    urza_a = _owner(connection_id=connection_a.id)
    repo = FakeArchiveRepository(
        [
            ("substation", station),
            ("connection", connection_a),
            ("connection", connection_b),
            ("urza", urza_a),
            ("urza", urza_b),
        ],
        connections=[connection_b, connection_a],
        urzas=[urza_b, urza_a],
    )
    service, _ = _service(repo)

    await service.archive(
        actor_id=uuid4(),
        object_type="substation",
        object_id=station.id,
        reason="Причина",
    )

    expected_connections = sorted([connection_a.id, connection_b.id])
    expected_urzas = sorted([urza_a.id, urza_b.id])
    assert repo.lock_calls == [
        ("substation", station.id),
        *(("connection", item_id) for item_id in expected_connections),
        *(("urza", item_id) for item_id in expected_urzas),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["connection", "urza"])
async def test_single_branch_archive_locks_parent_chain_in_order(kind):
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    repo = FakeArchiveRepository(
        [("substation", station), ("connection", connection), ("urza", urza)],
        connections=[connection],
        urzas=[urza],
    )
    service, _ = _service(repo)
    target = connection if kind == "connection" else urza

    await service.archive(
        actor_id=uuid4(),
        object_type=kind,
        object_id=target.id,
        reason="Причина",
    )

    assert repo.lock_calls[: (2 if kind == "connection" else 3)] == [
        ("substation", station.id),
        ("connection", connection.id),
        *([("urza", urza.id)] if kind == "urza" else []),
    ]


@pytest.mark.asyncio
async def test_history_delegates_access_and_returns_repository_order():
    station = _owner()
    repo = FakeArchiveRepository([("substation", station)])
    events = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    repo.get_history = AsyncMock(return_value=events)
    service, access = _service(repo)

    result = await service.get_history(
        actor_id=uuid4(), object_type="substation", object_id=station.id
    )

    assert result == events
    access.can_access_substation.assert_awaited_once_with(
        user_id=access.user_repository.get_by_id.await_args.args[0],
        substation_id=station.id,
    )
    repo.get_history.assert_awaited_once_with("substation", station.id)
