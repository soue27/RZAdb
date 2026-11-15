from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.infrastructure.monitor import notify


class FakeSession:
    def __init__(self, recipients):
        self.recipients = recipients
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def scalars(self, statement):
        self.statement = statement
        return SimpleNamespace(all=lambda: self.recipients)


class FakeSender:
    sent: ClassVar[list[dict]] = []
    failure = None

    def __init__(self, _settings):
        pass

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        if self.failure:
            raise self.failure


@pytest.mark.asyncio
async def test_health_notification_only_uses_active_superadmin(monkeypatch):
    session = FakeSession(["superadmin@example.test"])
    FakeSender.sent = []
    FakeSender.failure = None
    monkeypatch.setattr(notify, "async_session_factory", lambda: session)
    monkeypatch.setattr(notify, "SMTPEmailSender", FakeSender)

    result = await notify.send_health_notification(
        {"failures": ["backup failed"], "recoveries": []}
    )

    assert result == 0
    assert len(FakeSender.sent) == 1
    assert FakeSender.sent[0]["to"] == "superadmin@example.test"
    statement = str(session.statement)
    assert "users.role" in statement
    assert "active IS true" in statement
    assert "deleted_at IS NULL" in statement


@pytest.mark.asyncio
async def test_health_notification_refuses_ambiguous_superadmins(monkeypatch):
    session = FakeSession(
        [
            "one@example.test",
            "two@example.test",
        ]
    )
    FakeSender.sent = []
    monkeypatch.setattr(notify, "async_session_factory", lambda: session)
    monkeypatch.setattr(notify, "SMTPEmailSender", FakeSender)

    result = await notify.send_health_notification(
        {"failures": ["backup failed"], "recoveries": []}
    )

    assert result == 2
    assert FakeSender.sent == []


@pytest.mark.asyncio
async def test_smtp_error_does_not_leak_error_text_or_mask_failure(monkeypatch, caplog):
    session = FakeSession(["superadmin@example.test"])
    FakeSender.sent = []
    FakeSender.failure = RuntimeError("private SMTP response")
    monkeypatch.setattr(notify, "async_session_factory", lambda: session)
    monkeypatch.setattr(notify, "SMTPEmailSender", FakeSender)

    result = await notify.send_health_notification(
        {"failures": ["backup failed"], "recoveries": []}
    )

    assert result == 1
    assert "RuntimeError" in caplog.text
    assert "private SMTP response" not in caplog.text


@pytest.mark.asyncio
async def test_invalid_payload_is_rejected_before_sending(monkeypatch):
    session = FakeSession(["superadmin@example.test"])
    FakeSender.sent = []
    monkeypatch.setattr(notify, "async_session_factory", lambda: session)
    monkeypatch.setattr(notify, "SMTPEmailSender", FakeSender)

    result = await notify.send_health_notification({"failures": "no"})

    assert result == 2
    assert FakeSender.sent == []
