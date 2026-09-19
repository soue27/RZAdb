from fastapi.testclient import TestClient

from app.presentation.app import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_file_service_dependency() -> None:
    client = TestClient(app)

    response = client.get("/di-check")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "FileService",
    }