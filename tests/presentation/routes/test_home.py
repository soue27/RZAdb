from fastapi.testclient import TestClient
from uuid6 import uuid7
import pytest

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user

from app.application.tree.schemas import EnterpriseTreeNode
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