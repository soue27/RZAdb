from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user


@pytest.fixture
def authenticated_client(system_user_id: UUID) -> Iterator[TestClient]:
    current_user = User(
        id=system_user_id,
        full_name="SYSTEM",
        role=UserRole.SUPERADMIN,
        email="system@rzadb.local",
        password_hash="test-hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_upload_file(authenticated_client: TestClient) -> None:
    client = authenticated_client

    content = b"test pdf content"

    response = client.post(
        "/files",
        files={
            "file": (
                "scan.pdf",
                content,
                "application/pdf",
            ),
        },
        data={
            "display_name": "ПС Тестовая — ТО — 2026-09-19",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["original_name"] == "scan.pdf"
    assert data["display_name"] == "ПС Тестовая — ТО — 2026-09-19"
    assert data["extension"] == ".pdf"
    assert data["size"] == len(content)
    assert data["mime_type"] == "application/pdf"
    assert "id" in data
    assert "uploaded_at" in data
    assert "s3_key" not in data


def test_upload_file_without_file(authenticated_client: TestClient) -> None:
    client = authenticated_client

    response = client.post(
        "/files",
        data={
            "display_name": "ПС Тестовая",
        },
    )

    assert response.status_code == 422


def test_upload_file_without_display_name(authenticated_client: TestClient) -> None:
    client = authenticated_client

    response = client.post(
        "/files",
        files={
            "file": (
                "scan.pdf",
                b"test pdf content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_view_file(authenticated_client: TestClient) -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        content = b"test pdf content"

        upload_response = await client.post(
            "/files",
            files={
                "file": (
                    "scan.pdf",
                    content,
                    "application/pdf",
                ),
            },
            data={
                "display_name": "ПС Тестовая — ТО — 2026-09-19",
            },
        )

        assert upload_response.status_code == 200

        file_id = upload_response.json()["id"]

        view_response = await client.get(
            f"/files/{file_id}/view",
        )

    assert view_response.status_code == 200
    assert view_response.content == content
    assert view_response.headers["content-type"] == "application/pdf"
    assert (
        view_response.headers["content-disposition"]
        == 'inline; filename="scan.pdf"'
    )


@pytest.mark.asyncio
async def test_download_file(authenticated_client: TestClient) -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        content = b"test pdf content"

        upload_response = await client.post(
            "/files",
            files={
                "file": (
                    "scan.pdf",
                    content,
                    "application/pdf",
                ),
            },
            data={
                "display_name": "ПС Тестовая — ТО — 2026-09-19",
            },
        )

        assert upload_response.status_code == 200

        file_id = upload_response.json()["id"]

        download_response = await client.get(
            f"/files/{file_id}/download",
        )

    assert download_response.status_code == 200
    assert download_response.content == content
    assert download_response.headers["content-type"] == "application/pdf"
    assert (
        download_response.headers["content-disposition"]
        == 'attachment; filename="scan.pdf"'
    )


@pytest.mark.asyncio
async def test_view_missing_file(authenticated_client: TestClient) -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/files/{uuid4()}/view",
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Файл не найден."}


@pytest.mark.asyncio
async def test_download_missing_file(authenticated_client: TestClient) -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/files/{uuid4()}/download",
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Файл не найден."}
