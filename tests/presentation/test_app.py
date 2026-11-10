import logging
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import app.presentation.app as app_module
from app.core.config import Settings
from app.infrastructure.emailing.error_notifications import ErrorEmailConfigurationError
from app.presentation.app import app, create_app
from app.presentation.routes import health as health_module


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }
    request_id = UUID(response.headers["X-Request-ID"])
    assert request_id.version == 7


@pytest.mark.asyncio
async def test_readiness_executes_read_only_database_query(monkeypatch):
    class Session:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

        async def execute(self, statement):
            assert str(statement) == "SELECT 1"

    session = Session()
    monkeypatch.setattr(health_module, "async_session_factory", lambda: session)

    assert await health_module.readiness() == {"status": "ready"}
    assert session.closed


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_query_fails(monkeypatch):
    class Session:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

        async def execute(self, _statement):
            raise SQLAlchemyError("database unavailable")

    session = Session()
    monkeypatch.setattr(health_module, "async_session_factory", lambda: session)

    with pytest.raises(HTTPException) as exc_info:
        await health_module.readiness()

    assert exc_info.value.status_code == 503
    assert session.closed


def _settings(**overrides):
    values = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/rzadb",
        "session_secret": "test-secret",
    }
    values.update(overrides)
    return Settings(**values)


def _alert_handlers():
    return [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_rzadb_error_email_handler", False)
    ]


def test_empty_error_email_to_does_not_install_handler():
    settings = _settings(error_email_to="   ")
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        web_app = create_app()
        with TestClient(web_app):
            assert _alert_handlers() == []
    assert _alert_handlers() == []


def test_session_cookie_secure_setting_is_configurable():
    settings = _settings(session_cookie_secure=True)
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        web_app = create_app()

    session_middleware = next(
        middleware
        for middleware in web_app.user_middleware
        if middleware.cls is app_module.SessionMiddleware
    )
    assert session_middleware.kwargs["https_only"] is True


def test_session_cookie_secure_defaults_to_local_http_compatible_value():
    settings = _settings()
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        web_app = create_app()

    session_middleware = next(
        middleware
        for middleware in web_app.user_middleware
        if middleware.cls is app_module.SessionMiddleware
    )
    assert session_middleware.kwargs["https_only"] is False


def test_alert_handler_is_installed_at_startup_and_removed_at_shutdown():
    settings = _settings(
        error_email_to="alerts@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="smtp-secret-password",
        smtp_from_email="sender@example.com",
        smtp_starttls=True,
    )
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        web_app = create_app()
        with TestClient(web_app):
            handlers = _alert_handlers()
            assert len(handlers) == 1
            assert handlers[0] is web_app.state.error_email_handler
        assert _alert_handlers() == []


def test_invalid_alert_configuration_fails_during_startup():
    settings = _settings(
        error_email_to="alerts@example.com",
        smtp_from_email="sender@example.com",
    )
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        web_app = create_app()
        with (
            pytest.raises(ErrorEmailConfigurationError, match="SMTP_HOST"),
            TestClient(web_app),
        ):
            pass


def test_overlapping_lifespans_reuse_one_handler():
    settings = _settings(
        error_email_to="alerts@example.com",
        smtp_host="smtp.example.com",
        smtp_from_email="sender@example.com",
        smtp_starttls=True,
    )
    with (
        patch.object(app_module, "get_settings", return_value=settings),
        patch.object(app_module, "configure_logging"),
    ):
        first_app = create_app()
        second_app = create_app()
        with TestClient(first_app):
            first_handler = first_app.state.error_email_handler
            with TestClient(second_app):
                assert second_app.state.error_email_handler is first_handler
                assert len(_alert_handlers()) == 1
            assert len(_alert_handlers()) == 1
        assert _alert_handlers() == []
