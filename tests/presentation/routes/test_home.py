from fastapi.testclient import TestClient
from uuid6 import uuid7
import pytest

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user

from app.application.tree.schemas import (
    ConnectionTreeNode,
    EnterpriseTreeNode,
    SubstationTreeNode,
    URZATreeNode,
)
from app.presentation.dependencies.services import get_tree_service


def make_user() -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
    )

class FakeTreeService:
    def __init__(self, tree: list[EnterpriseTreeNode]) -> None:
        self.tree = tree

    async def get_tree(self, user_id):
        return self.tree

def make_tree(root_type: str, root_name: str) -> list[EnterpriseTreeNode]:
    return [
        EnterpriseTreeNode(
            id=uuid7(),
            type=root_type,
            full_name=root_name,
            short_name=root_name,
        )
    ]

def make_tree_with_substation() -> tuple[
    list[EnterpriseTreeNode],
    str,
]:
    substation_id = uuid7()

    substation = SubstationTreeNode(
        id=substation_id,
        dispatch_name="ПС Активная",
        connections=[],
    )

    tree = [
        EnterpriseTreeNode(
            id=uuid7(),
            type="holding",
            full_name="Россети Урал",
            short_name="Россети Урал",
            substations=[substation],
        )
    ]

    return tree, str(substation_id)

def make_tree_with_connection() -> tuple[
    list[EnterpriseTreeNode],
    dict[str, str],
]:
    urza_id = uuid7()
    connection_id = uuid7()
    substation_id = uuid7()

    urza = URZATreeNode(
        id=urza_id,
        dispatch_name="УРЗА-1",
    )

    connection = ConnectionTreeNode(
        id=connection_id,
        dispatch_name="Присоединение 1",
        urzas=[urza],
    )

    substation = SubstationTreeNode(
        id=substation_id,
        dispatch_name="ПС Активная",
        connections=[connection],
    )

    tree = [
        EnterpriseTreeNode(
            id=uuid7(),
            type="holding",
            full_name="Россети Урал",
            short_name="Россети Урал",
            substations=[substation],
        )
    ]

    return tree, {
        "substation": str(substation_id),
        "connection": str(connection_id),
        "urza": str(urza_id),
    }

def test_home_renders_separate_connection_expand_and_select_controls() -> None:
    user = make_user()
    tree, object_ids = make_tree_with_connection()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(tree=tree)

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200

        assert (
            f'data-bs-target="#tree-connection-{object_ids["connection"]}"'
            in response.text
        )

        assert (
            f'data-object-type="connection"'
            in response.text
        )

        assert (
            f'data-object-id="{object_ids["connection"]}"'
            in response.text
        )

    finally:
        app.dependency_overrides.clear()


def test_home_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 401


def test_home_authenticated() -> None:
    user = make_user()

    async def override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_current_user

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "RZAdb" in response.text
        assert "Тестовый пользователь" in response.text
    finally:
        app.dependency_overrides.clear()

@pytest.mark.parametrize(
    ("root_type", "root_name"),
    [
        ("holding", "Россети Урал"),
        ("branch", "Свердловский филиал"),
        ("department", "ПО Центральные сети"),
    ],
)
def test_home_renders_tree_root_types(
    root_type: str,
    root_name: str,
) -> None:
    user = make_user()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(
        tree=make_tree(root_type, root_name),
    )

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert root_name in response.text
    finally:
        app.dependency_overrides.clear()

def test_home_renders_substation_object_attributes() -> None:
    user = make_user()

    tree, substation_id = make_tree_with_substation()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(tree=tree)

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert "ПС Активная" in response.text
        assert 'data-object-type="substation"' in response.text
        assert f'data-object-id="{substation_id}"' in response.text
    finally:
        app.dependency_overrides.clear()

def test_home_renders_object_attributes_for_tree_chain() -> None:
    user = make_user()

    tree, object_ids = make_tree_with_connection()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(tree=tree)

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200

        assert (
            'data-object-type="substation"' in response.text
        )
        assert (
            f'data-object-id="{object_ids["substation"]}"'
            in response.text
        )

        assert (
            'data-object-type="connection"' in response.text
        )
        assert (
            f'data-object-id="{object_ids["connection"]}"'
            in response.text
        )

        assert 'data-object-type="urza"' in response.text
        assert (
            f'data-object-id="{object_ids["urza"]}"'
            in response.text
        )
    finally:
        app.dependency_overrides.clear()


def test_home_renders_htmx_attributes_for_substation() -> None:
    user = make_user()
    tree, substation_id = make_tree_with_substation()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(tree=tree)

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert (
            f'hx-get="/objects/substation/{substation_id}"'
            in response.text
        )
        assert 'hx-target="#object-content"' in response.text
        assert 'hx-swap="innerHTML"' in response.text
    finally:
        app.dependency_overrides.clear()


def test_home_renders_htmx_attributes_for_connection() -> None:
    user = make_user()
    tree, object_ids = make_tree_with_connection()

    async def override_current_user() -> User:
        return user

    fake_tree_service = FakeTreeService(tree=tree)

    def override_tree_service() -> FakeTreeService:
        return fake_tree_service

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_tree_service] = override_tree_service

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert (
            f'hx-get="/objects/connection/{object_ids["connection"]}"'
            in response.text
        )
        assert 'hx-target="#object-content"' in response.text
        assert 'hx-swap="innerHTML"' in response.text
    finally:
        app.dependency_overrides.clear()