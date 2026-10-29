from unittest.mock import AsyncMock, Mock

import pytest

from app.application.email_digest.service import DigestRunResult

from app.infrastructure.emailing import send_email_digest as cli



@pytest.mark.asyncio
async def test_run_email_digest_wires_service_and_closes_session(
    monkeypatch,
):
    settings = Mock()
    sender = Mock()
    session = Mock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session

    session_factory = Mock(return_value=session_context)
    service_instance = Mock()
    service_instance.send_digests = AsyncMock(
        return_value=DigestRunResult(recipients=2, sent=2)
    )
    service_factory = Mock(return_value=service_instance)

    monkeypatch.setattr(cli, "get_settings", Mock(return_value=settings))
    monkeypatch.setattr(cli, "SMTPEmailSender", Mock(return_value=sender))
    monkeypatch.setattr(cli, "async_session_factory", session_factory)
    monkeypatch.setattr(cli, "EmailDigestService", service_factory)

    result = await cli.run_email_digest()

    assert result.recipients == 2
    assert result.sent == 2
    cli_settings = cli.get_settings
    cli_settings.assert_called_once_with()
    session_factory.assert_called_once_with()
    service_factory.assert_called_once()
    service_instance.send_digests.assert_awaited_once_with()
    session_context.__aexit__.assert_awaited_once()


def test_main_exits_zero_when_all_emails_sent(monkeypatch):
    async def fake_run():
        return DigestRunResult(recipients=2, sent=2)

    monkeypatch.setattr(cli, "run_email_digest", fake_run)

    cli.main()


def test_main_exits_one_when_delivery_failed(monkeypatch):
    async def fake_run():
        return DigestRunResult(recipients=2, sent=1, failed=1)

    monkeypatch.setattr(cli, "run_email_digest", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1


def test_main_exits_one_when_run_raises(monkeypatch):
    async def fake_run():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(cli, "run_email_digest", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
