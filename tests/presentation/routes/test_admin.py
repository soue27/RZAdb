
import json
import re
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.request_context import bind_user_id, get_request_context
from app.domain.enums import AccessCategory, EnterpriseType, UserRole
from app.domain.user import User
from app.infrastructure.backup.coordinator import (
    BackupDisabledError,
    BackupError,
    BackupManifestError,
)
from app.infrastructure.backup.run_lock import BackupRunLock
from app.presentation.routes.admin import _read_backup_status
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user


def make_user(role: UserRole) -> User:
    return User(
        id=uuid4(),
        full_name="Тестовый пользователь",
        role=role,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=uuid4(),
        updated_by=uuid4(),
    )


@pytest.fixture
def client():
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def override_user(user: User) -> None:
    async def get_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = get_user


def wait_for_backup_status(client, expected_status: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get("/admin/backup/status")
        if response.status_code == 200 and response.json()["status"] == expected_status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Backup did not reach status {expected_status}")


def backup_settings(tmp_path, *, enabled=True):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@localhost/rzadb",
        session_secret="test-secret",
        backup_enabled=enabled,
        backup_local_enabled=True,
        backup_local_dir=tmp_path,
        backup_local_retention_count=2,
        backup_email_enabled=False,
        backup_yandex_disk_enabled=False,
    )


def make_enterprise():
    return SimpleNamespace(
        id=uuid4(),
        full_name="Тестовое предприятие",
        short_name="Тестовое предприятие",
        type=EnterpriseType.DEPARTMENT,
    )


def test_admin_requires_authentication(client):
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_admin_backup_worker_does_not_inherit_request_context(client, tmp_path):
    observed_contexts = []

    async def authenticated_user():
        bind_user_id("authenticated-user")
        return make_user(UserRole.SUPERADMIN)

    app.dependency_overrides[get_current_user] = authenticated_user

    class FakeLock:
        def __init__(self, directory):
            self.directory = directory

        def acquire(self):
            return None

        def release(self):
            return None

    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    def observe_worker_context(settings, lock):
        observed_contexts.append(get_request_context())

    with (
        patch(
            "app.presentation.routes.admin.get_settings",
            return_value=backup_settings(tmp_path),
        ),
        patch("app.presentation.routes.admin.BackupRunLock", FakeLock),
        patch("app.presentation.routes.admin.threading.Thread", InlineThread),
        patch("app.presentation.routes.admin._write_backup_status"),
        patch(
            "app.presentation.routes.admin._run_backup_in_thread",
            observe_worker_context,
        ),
    ):
        response = client.post("/admin/backup")

    assert response.status_code == 200
    assert len(observed_contexts) == 1
    assert observed_contexts[0] is None


def test_admin_rejects_engineer(client):
    override_user(make_user(UserRole.ENGINEER))

    response = client.get("/admin/")

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.ENGINEER])
def test_user_creation_route_rejects_non_superadmin(client, role):
    override_user(make_user(role))

    response = client.post(
        "/admin/users",
        data={
            "full_name": "Пользователь",
            "email": "new@example.com",
            "role": "superadmin",
            "access_category": "IV",
            "temporary_password": "TemporaryPassword123",
        },
    )

    assert response.status_code == 403


def test_admin_renders_users_and_enterprises(client):
    override_user(make_user(UserRole.SUPERADMIN))
    enterprise = make_enterprise()
    user = make_user(UserRole.ENGINEER)
    user.enterprise = enterprise

    with (
        patch(
            "app.presentation.routes.admin.EnterpriseRepository"
        ) as enterprise_repo_cls,
        patch(
            "app.presentation.routes.admin.UserRepository"
        ) as user_repo_cls,
    ):
        enterprise_repo_cls.return_value.get_all_for_access_scope = AsyncMock(
            return_value=[enterprise]
        )
        user_repo_cls.return_value.get_all = AsyncMock(return_value=[user])

        response = client.get("/admin/")

    assert response.status_code == 200
    assert "Администрирование" in response.text
    assert "test@example.com" in response.text
    assert "Тестовое предприятие" in response.text
    assert 'name="role_filter"' in response.text
    assert 'name="status_filter"' in response.text
    assert 'name="enterprise_filter"' in response.text
    assert "Резервное копирование PostgreSQL" in response.text
    assert "Создать резервную копию" in response.text


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.ENGINEER])
def test_backup_routes_reject_non_superadmin(client, role):
    override_user(make_user(role))

    start_response = client.post("/admin/backup")
    status_response = client.get("/admin/backup/status")

    assert start_response.status_code == 403
    assert status_response.status_code == 403


def test_backup_routes_require_authentication(client):
    assert client.post("/admin/backup", follow_redirects=False).status_code == 303
    assert client.get("/admin/backup/status", follow_redirects=False).status_code == 303


def test_superadmin_starts_backup_once_and_receives_safe_success_result(
    client, tmp_path, monkeypatch
):
    override_user(make_user(UserRole.SUPERADMIN))
    settings = backup_settings(tmp_path)
    monkeypatch.setattr("app.presentation.routes.admin.get_settings", lambda: settings)
    calls = []

    class FakeCoordinator:
        def __init__(self, coordinator_settings):
            assert coordinator_settings is settings

        async def run(self):
            calls.append("run")
            return {
                "run_id": "run-123",
                "status": "success",
                "started_at": "2026-11-08T10:00:00+00:00",
                "duration_seconds": 12.5,
                "size_bytes": 256,
                "sha256": "abc123",
                "dump_path": "/private/backups/secret.dump",
                "manifest_path": "/private/backups/secret.json",
                "error": None,
                "channels": {
                    "local": {"enabled": True, "status": "success", "path": "secret"},
                    "email": {"enabled": False, "status": "disabled"},
                    "yandex_disk": {"enabled": False, "status": "disabled"},
                },
            }

    monkeypatch.setattr(
        "app.presentation.routes.admin.BackupCoordinator", FakeCoordinator
    )

    start_response = client.post("/admin/backup")
    state = wait_for_backup_status(client, "success")

    assert start_response.status_code == 200
    assert calls == ["run"]
    assert state["run_id"] == "run-123"
    assert state["started_at"] == "2026-11-08T10:00:00+00:00"
    assert state["duration_seconds"] == 12.5
    assert state["size_bytes"] == 256
    assert state["sha256"] == "abc123"
    assert state["channels"]["local"]["status"] == "success"
    serialized = start_response.text + str(state)
    assert "/private/backups" not in serialized
    assert "manifest_path" not in serialized
    assert "traceback" not in serialized.lower()


def test_backup_status_endpoint_returns_partial_success_to_htmx(
    client, tmp_path, monkeypatch
):
    override_user(make_user(UserRole.SUPERADMIN))
    settings = backup_settings(tmp_path)
    monkeypatch.setattr("app.presentation.routes.admin.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.presentation.routes.admin._read_backup_status",
        lambda _settings: {
            "run_id": "run-partial",
            "status": "partial_success",
            "started_at": "2026-11-08T10:00:00+00:00",
            "duration_seconds": 4.0,
            "size_bytes": 128,
            "sha256": "sha256-value",
            "error": None,
            "channels": {
                "local": {"enabled": True, "status": "success"},
                "email": {"enabled": True, "status": "failed", "error": "Email channel error"},
                "yandex_disk": {"enabled": True, "status": "success"},
            },
        },
    )

    response = client.get(
        "/admin/backup/status", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert "Частично успешно" in response.text
    assert "Email" in response.text
    assert "Ошибка отправки резервной копии по электронной почте." in response.text
    assert "sha256-value" in response.text
    assert "/private/" not in response.text


def test_running_backup_rejects_duplicate_request(client, tmp_path, monkeypatch):
    override_user(make_user(UserRole.SUPERADMIN))
    settings = backup_settings(tmp_path)
    monkeypatch.setattr("app.presentation.routes.admin.get_settings", lambda: settings)
    calls = []

    class FakeCoordinator:
        def __init__(self, settings):
            pass

        async def run(self):
            calls.append("run")

    monkeypatch.setattr(
        "app.presentation.routes.admin.BackupCoordinator", FakeCoordinator
    )
    lock = BackupRunLock(tmp_path).acquire()
    try:
        response = client.post("/admin/backup")
    finally:
        lock.release()

    assert response.status_code == 409
    assert response.json()["error"] == "Резервное копирование уже выполняется."
    assert calls == []


def test_status_rereads_state_after_lock_before_marking_interrupted(
    tmp_path, monkeypatch
):
    settings = backup_settings(tmp_path)
    state_path = tmp_path / ".admin-backup-status.json"
    running_state = {
        "run_id": "run-123",
        "status": "running",
        "started_at": "2026-11-08T10:00:00+00:00",
        "channels": {},
    }
    state_path.write_text(json.dumps(running_state), encoding="utf-8")

    class FinishingBackupLock:
        def __init__(self, backup_dir):
            self.lock = BackupRunLock(backup_dir)

        def acquire(self):
            self.lock.acquire()
            state_path.write_text(
                json.dumps({**running_state, "status": "success", "error": None}),
                encoding="utf-8",
            )
            return self

        def release(self):
            self.lock.release()

    monkeypatch.setattr(
        "app.presentation.routes.admin.BackupRunLock", FinishingBackupLock
    )

    result = _read_backup_status(settings)
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["error"] is None
    assert persisted["status"] == "success"


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (BackupDisabledError, "отключено настройкой BACKUP_ENABLED"),
        (BackupManifestError, "сохранить манифест"),
        (BackupError, "завершилось ошибкой"),
        (RuntimeError, "Внутренняя ошибка"),
    ],
)
def test_backup_errors_are_safe_and_release_the_lock(
    client, tmp_path, monkeypatch, error_type, expected_message
):
    override_user(make_user(UserRole.SUPERADMIN))
    settings = backup_settings(tmp_path)
    monkeypatch.setattr("app.presentation.routes.admin.get_settings", lambda: settings)

    class FakeCoordinator:
        def __init__(self, settings):
            pass

        async def run(self):
            raise error_type("secret password /private/path traceback")

    monkeypatch.setattr(
        "app.presentation.routes.admin.BackupCoordinator", FakeCoordinator
    )

    client.post("/admin/backup")
    state = wait_for_backup_status(client, "failed")
    assert expected_message in state["error"]
    assert "password" not in state["error"]
    assert "/private" not in str(state)

    # The lock was released by the worker even when the coordinator raised.
    lock = BackupRunLock(tmp_path).acquire()
    lock.release()


@pytest.mark.parametrize(
    ("params", "expected_detail"),
    [
        (
            {"role_filter": "unknown"},
            "Неизвестная роль пользователя.",
        ),
        (
            {"status_filter": "unknown"},
            "Неизвестный статус пользователя.",
        ),
        (
            {"enterprise_filter": "not-a-uuid"},
            "Некорректный идентификатор предприятия.",
        ),
    ],
)
def test_admin_rejects_invalid_filters(client, params, expected_detail):
    override_user(make_user(UserRole.SUPERADMIN))

    response = client.get("/admin/", params=params)

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_admin_passes_filters_to_user_repository(client):
    override_user(make_user(UserRole.SUPERADMIN))
    enterprise_id = uuid4()

    with (
        patch(
            "app.presentation.routes.admin.EnterpriseRepository"
        ) as enterprise_repo_cls,
        patch(
            "app.presentation.routes.admin.UserRepository"
        ) as user_repo_cls,
    ):
        enterprise_repo_cls.return_value.get_all_for_access_scope = AsyncMock(
            return_value=[]
        )
        user_repo_cls.return_value.get_all = AsyncMock(return_value=[])

        response = client.get(
            "/admin/",
            params={
                "role_filter": "engineer",
                "status_filter": "active",
                "enterprise_filter": str(enterprise_id),
            },
        )

        assert response.status_code == 200
        user_repo_cls.return_value.get_all.assert_awaited_once_with(
            role=UserRole.ENGINEER,
            status_filter="active",
            enterprise_id=enterprise_id,
            without_enterprise=False,
        )


def test_admin_filters_users_without_enterprise(client):
    override_user(make_user(UserRole.SUPERADMIN))

    with (
        patch(
            "app.presentation.routes.admin.EnterpriseRepository"
        ) as enterprise_repo_cls,
        patch(
            "app.presentation.routes.admin.UserRepository"
        ) as user_repo_cls,
    ):
        enterprise_repo_cls.return_value.get_all_for_access_scope = AsyncMock(
            return_value=[]
        )
        user_repo_cls.return_value.get_all = AsyncMock(return_value=[])

        response = client.get(
            "/admin/",
            params={"enterprise_filter": "none"},
        )

        assert response.status_code == 200
        user_repo_cls.return_value.get_all.assert_awaited_once_with(
            role=None,
            status_filter=None,
            enterprise_id=None,
            without_enterprise=True,
        )

def test_admin_preserves_selected_filter_values(client):
    override_user(make_user(UserRole.SUPERADMIN))
    enterprise = make_enterprise()

    with (
        patch("app.presentation.routes.admin.EnterpriseRepository") as enterprise_repo_cls,
        patch("app.presentation.routes.admin.UserRepository") as user_repo_cls,
    ):
        enterprise_repo_cls.return_value.get_all_for_access_scope = AsyncMock(
            return_value=[enterprise],
        )
        user_repo_cls.return_value.get_all = AsyncMock(return_value=[])

        response = client.get(
            "/admin/",
            params={
                "role_filter": "engineer",
                "status_filter": "active",
                "enterprise_filter": str(enterprise.id),
            },
        )

    assert response.status_code == 200

    html = response.text

    assert re.search(
        r'<option\s+value="engineer"\s+selected',
        html,
    )
    assert re.search(
        r'<option\s+value="active"\s+selected',
        html,
    )
    assert re.search(
        rf'<option\s+value="{enterprise.id}"\s+selected',
        html,
    )
