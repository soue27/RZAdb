
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AccessCategory, EnterpriseType, UserRole
from app.domain.user import User
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


def make_enterprise():
    return SimpleNamespace(
        id=uuid4(),
        full_name="Тестовое предприятие",
        short_name="Тестовое предприятие",
        type=EnterpriseType.DEPARTMENT,
    )


def test_admin_requires_authentication(client):
    response = client.get("/admin/")

    assert response.status_code == 401


def test_admin_rejects_engineer(client):
    override_user(make_user(UserRole.ENGINEER))

    response = client.get("/admin/")

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
