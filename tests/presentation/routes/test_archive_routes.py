from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.archive_service import ArchiveBlocker, ArchiveService
from app.domain.enums import ArchiveEventType, TaskStatus, UserRole
from app.infrastructure.database.session import get_session
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_access_service,
    get_archive_service,
    get_inspection_task_repository,
    get_task_repository,
)


class FakeArchiveRepository:
    def __init__(self, objects, *, blockers=(), history=()):
        self.objects = {(kind, item.id): item for kind, item in objects}
        self.blockers = list(blockers)
        self.history = list(history)
        self.events = []

    async def get_object(self, kind, object_id):
        return self.objects.get((kind, object_id))

    async def lock_object(self, kind, object_id):
        return await self.get_object(kind, object_id)

    async def get_active_connections(self, substation_id):
        return [
            item
            for (kind, _), item in self.objects.items()
            if kind == "connection"
            and item.substation_id == substation_id
            and item.deleted_at is None
        ]

    async def get_active_urzas(self, connection_ids):
        return [
            item
            for (kind, _), item in self.objects.items()
            if kind == "urza"
            and item.connection_id in connection_ids
            and item.deleted_at is None
        ]

    async def get_blocking_processes(self, **kwargs):
        return [
            (item.process_type, item.process_id, item.status)
            if isinstance(item, ArchiveBlocker)
            else item
            for item in self.blockers
        ]

    async def add_events(self, events):
        self.events.extend(events)

    async def get_history(self, kind, object_id):
        return self.history


class FakeAccessService:
    def __init__(self, user, accessible_ids):
        self.user_repository = SimpleNamespace(
            get_by_id=lambda _user_id: self._get_user()
        )
        self.user = user
        self.accessible_ids = set(accessible_ids)
        self.substation_repository = SimpleNamespace()
        self.enterprise_repository = SimpleNamespace()
        self.connection_repository = SimpleNamespace()
        self.urza_repository = SimpleNamespace()

    async def _get_user(self):
        return self.user

    async def can_access_substation(self, user_id, substation_id):
        return substation_id in self.accessible_ids

    async def can_access_connection(self, user_id, connection_id):
        return connection_id in self.accessible_ids

    async def can_access_urza(self, user_id, urza_id):
        return urza_id in self.accessible_ids


class FakeTaskRepository:
    def __init__(self, tasks=()):
        self.tasks = {task.id: task for task in tasks}

    async def get_active_by_id(self, task_id):
        task = self.tasks.get(task_id)
        return task if task is not None and task.deleted_at is None else None


class FakeInspectionRepository:
    def __init__(self, tasks=()):
        self.tasks = {task.id: task for task in tasks}

    async def get_active_by_id(self, task_id):
        task = self.tasks.get(task_id)
        return task if task is not None and task.deleted_at is None else None


def _owner(**values):
    return SimpleNamespace(id=uuid7(), deleted_at=None, deleted_by=None, **values)


def _install(
    *,
    kind="substation",
    role=UserRole.MANAGER,
    blockers=(),
    tasks=(),
    inspections=(),
    history=(),
    accessible_ids=None,
    archived=False,
):
    user = SimpleNamespace(id=uuid7(), role=role)
    station = _owner()
    connection = _owner(substation_id=station.id)
    urza = _owner(connection_id=connection.id)
    target = {"substation": station, "connection": connection, "urza": urza}[kind]
    if archived:
        target.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
    objects = [
        ("substation", station),
        ("connection", connection),
        ("urza", urza),
    ]
    repository = FakeArchiveRepository(objects, blockers=blockers, history=history)
    access = FakeAccessService(
        user,
        accessible_ids
        if accessible_ids is not None
        else {station.id, connection.id, urza.id},
    )
    service = ArchiveService(repository, access)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _fail_if_database_session_is_requested
    app.dependency_overrides[get_archive_service] = lambda: service
    app.dependency_overrides[get_access_service] = lambda: access
    app.dependency_overrides[get_task_repository] = lambda: FakeTaskRepository(tasks)
    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionRepository(inspections)
    )
    return user, target, station, connection, urza, repository


def _fail_if_database_session_is_requested():
    raise AssertionError("HTTP archive route test must not request a database session")


@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
def test_preview_routes_cover_all_object_types(kind):
    user, target, *_ = _install(kind=kind)
    try:
        response = TestClient(app).get(f"/objects/{kind}/{target.id}/archive/preview")
        assert response.status_code == 200
        assert str(target.id) in response.text
        assert user.id.hex not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
@pytest.mark.parametrize("htmx", [False, True])
def test_archive_success_uses_post_redirect_contract(kind, htmx):
    _, target, *_ = _install(kind=kind)
    headers = {"HX-Request": "true"} if htmx else {}
    try:
        response = TestClient(app).post(
            f"/objects/{kind}/{target.id}/archive",
            data={"reason": "Плановая замена"},
            headers=headers,
            follow_redirects=False,
        )
        if htmx:
            assert response.status_code == 204
            assert response.headers["HX-Redirect"].endswith("?archived=true")
        else:
            assert response.status_code == 303
            assert response.headers["location"].endswith("?archived=true")
        assert target.deleted_at is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("htmx", [False, True])
def test_archive_noop_keeps_success_contract(htmx):
    _, target, *_ = _install(kind="substation", archived=True)
    old_deleted_at = target.deleted_at
    headers = {"HX-Request": "true"} if htmx else {}
    try:
        response = TestClient(app).post(
            f"/objects/substation/{target.id}/archive",
            data={"reason": "Повтор"},
            headers=headers,
            follow_redirects=False,
        )
        assert response.status_code == (204 if htmx else 303)
        assert target.deleted_at == old_deleted_at
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
@pytest.mark.parametrize("htmx", [False, True])
def test_restore_noop_uses_success_contract(kind, htmx):
    _, target, *_ = _install(kind=kind)
    headers = {"HX-Request": "true"} if htmx else {}
    try:
        response = TestClient(app).post(
            f"/objects/{kind}/{target.id}/restore",
            headers=headers,
            follow_redirects=False,
        )
        assert response.status_code == (204 if htmx else 303)
        assert response.headers.get(
            "HX-Redirect", response.headers.get("location")
        ) == (f"/objects/{kind}/{target.id}")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
@pytest.mark.parametrize("htmx", [False, True])
def test_restore_success_uses_post_redirect_contract(kind, htmx):
    _, target, *_ = _install(kind=kind, archived=True)
    target.deleted_by = uuid7()
    headers = {"HX-Request": "true"} if htmx else {}
    try:
        response = TestClient(app).post(
            f"/objects/{kind}/{target.id}/restore",
            data={"reason": "Восстановление"},
            headers=headers,
            follow_redirects=False,
        )
        assert response.status_code == (204 if htmx else 303)
        assert (
            response.headers.get("HX-Redirect", response.headers.get("location"))
            == f"/objects/{kind}/{target.id}"
        )
        assert target.deleted_at is None
        assert target.deleted_by is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("htmx", [False, True])
def test_archive_blocker_returns_409_with_only_accessible_processes(htmx):
    blocker_id = uuid4()
    hidden_id = uuid4()
    inspection_id = uuid4()
    hidden_inspection_id = uuid4()
    blocker = ArchiveBlocker("task", blocker_id, TaskStatus.IN_PROGRESS)
    hidden = ArchiveBlocker("task", hidden_id, TaskStatus.ASSIGNED)
    task = SimpleNamespace(
        id=blocker_id,
        deleted_at=None,
        urza_id=uuid7(),
        substation_id=None,
        assigned_to=uuid7(),
    )
    hidden_task = SimpleNamespace(
        id=hidden_id,
        deleted_at=None,
        urza_id=uuid4(),
        substation_id=None,
        assigned_to=uuid7(),
    )
    inspection = SimpleNamespace(
        id=inspection_id, deleted_at=None, substation_id=uuid7()
    )
    hidden_inspection = SimpleNamespace(
        id=hidden_inspection_id, deleted_at=None, substation_id=uuid4()
    )
    _, target, station, connection, urza, repo = _install(
        kind="substation",
        blockers=[
            blocker,
            hidden,
            ArchiveBlocker("inspection", inspection_id, TaskStatus.CREATED),
            ArchiveBlocker("inspection", hidden_inspection_id, TaskStatus.ASSIGNED),
        ],
        tasks=[task, hidden_task],
        inspections=[inspection, hidden_inspection],
        accessible_ids=set(),
    )
    # The object itself is accessible, while only one blocker owner is in scope.
    access = app.dependency_overrides[get_access_service]()
    access.accessible_ids.update(
        {station.id, connection.id, urza.id, task.urza_id, inspection.substation_id}
    )
    headers = {"HX-Request": "true"} if htmx else {}

    try:
        response = TestClient(app).post(
            f"/objects/substation/{target.id}/archive",
            data={"reason": "Причина"},
            headers=headers,
        )
        assert response.status_code == 409
        assert str(blocker_id) in response.text
        assert str(hidden_id) not in response.text
        assert str(inspection_id) in response.text
        assert str(hidden_inspection_id) not in response.text
        assert target.deleted_at is None
        assert repo.events == []
        if not htmx:
            assert f"/objects/substation/{target.id}" in response.text
    finally:
        app.dependency_overrides.clear()


def test_invalid_reason_maps_to_400():
    _, target, *_ = _install(kind="substation")
    try:
        response = TestClient(app).post(
            f"/objects/substation/{target.id}/archive", data={"reason": "  "}
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("endpoint", ["archive/preview", "archive/history"])
def test_uuid_and_archived_query_do_not_bypass_role_or_scope(endpoint):
    _, target, *_ = _install(kind="substation", role=UserRole.ENGINEER)
    try:
        response = TestClient(app).get(
            f"/objects/substation/{target.id}/{endpoint}?archived=true"
        )
        assert response.status_code == 403
        assert target.id.hex not in response.text
    finally:
        app.dependency_overrides.clear()


def test_out_of_scope_history_id_is_denied():
    event = SimpleNamespace(
        id=uuid7(),
        event_type=ArchiveEventType.ARCHIVED,
        occurred_at=datetime.now(UTC),
        actor=SimpleNamespace(full_name="Private actor"),
        reason="Скрытая причина",
        operation_id=uuid7(),
    )
    _, target, *_ = _install(kind="connection", accessible_ids=set(), history=[event])
    try:
        response = TestClient(app).get(
            f"/objects/connection/{target.id}/archive/history"
        )
        assert response.status_code == 403
        assert "Скрытая причина" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_direct_archive_post_out_of_scope_is_denied_even_with_archived_query():
    _, target, *_ = _install(kind="urza", accessible_ids=set())
    try:
        response = TestClient(app).post(
            f"/objects/urza/{target.id}/archive?archived=true",
            data={"reason": "Причина"},
        )
        assert response.status_code == 403
        assert target.deleted_at is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["substation", "connection", "urza"])
def test_history_is_available_for_accessible_archived_objects(kind):
    event = SimpleNamespace(
        id=uuid7(),
        event_type=ArchiveEventType.ARCHIVED,
        occurred_at=datetime(2026, 10, 24, tzinfo=UTC),
        actor=SimpleNamespace(full_name="Архивировавший пользователь"),
        reason="Основание",
        operation_id=uuid7(),
    )
    _, target, *_ = _install(kind=kind, archived=True, history=[event])
    try:
        response = TestClient(app).get(f"/objects/{kind}/{target.id}/archive/history")
        assert response.status_code == 200
        assert "Архивировавший пользователь" in response.text
        assert "Основание" in response.text
    finally:
        app.dependency_overrides.clear()


def test_post_ignores_client_supplied_cascade_ids():
    _, station, _, connection, _, repo = _install(kind="substation")
    foreign_connection = _owner(substation_id=uuid4())
    repo.objects[("connection", foreign_connection.id)] = foreign_connection
    try:
        response = TestClient(app).post(
            f"/objects/substation/{station.id}/archive",
            data={
                "reason": "Причина",
                "connection_ids": str(foreign_connection.id),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        assert connection.deleted_at is not None
        assert foreign_connection.deleted_at is None
    finally:
        app.dependency_overrides.clear()
