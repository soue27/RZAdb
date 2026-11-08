from uuid import UUID

from fastapi.testclient import TestClient

from app.presentation.app import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }
    request_id = UUID(response.headers["X-Request-ID"])
    assert request_id.version == 7
