from fastapi.testclient import TestClient

from app.presentation.app import app


def test_upload_file() -> None:
    client = TestClient(app)

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

def test_upload_file_without_file() -> None:
    client = TestClient(app)

    response = client.post(
        "/files",
        data={
            "display_name": "ПС Тестовая",
        },
    )

    assert response.status_code == 422

def test_upload_file_without_display_name() -> None:
    client = TestClient(app)

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