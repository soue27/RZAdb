import asyncio
import logging
import threading

import pytest

from app.core.config import Settings
from app.core.request_context import (
    bind_user_id,
    reset_request_context,
    set_request_context,
)
from app.infrastructure.emailing.error_notifications import (
    ERROR_EMAIL_COOLDOWN_SECONDS,
    ErrorEmailConfigurationError,
    ErrorEmailNotificationHandler,
    _validate_address,
    validate_error_email_settings,
)


def make_settings(**overrides):
    values = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/rzadb",
        "session_secret": "test-secret",
        "error_email_to": "alerts@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "sender@example.com",
        "smtp_password": "smtp-secret-password",
        "smtp_from_email": "sender@example.com",
        "smtp_starttls": True,
        "smtp_use_ssl": False,
    }
    values.update(overrides)
    return Settings(**values)


class FakeSender:
    def __init__(self, send_impl=None):
        self.send_impl = send_impl
        self.calls = []

    async def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.send_impl is not None:
            await self.send_impl(**kwargs)


def make_record(
    *,
    level=logging.ERROR,
    name="app.example",
    message="operation failed",
    exc_info=None,
):
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="/secret/path.py",
        lineno=10,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def make_handler(*, queue_size=100, clock=lambda: 0.0, sender=None):
    return ErrorEmailNotificationHandler(
        recipient="alerts@example.com",
        sender=sender or FakeSender(),
        queue_size=queue_size,
        clock=clock,
    )


def test_alert_configuration_requires_complete_encrypted_smtp_settings():
    assert validate_error_email_settings(make_settings(error_email_to=None)) is None
    assert validate_error_email_settings(make_settings()) == "alerts@example.com"
    assert validate_error_email_settings(
        make_settings(smtp_starttls=False, smtp_use_ssl=True)
    ) == "alerts@example.com"


@pytest.mark.parametrize(
    "address",
    [
        "alerts@example.com",
        "alerts+rzadb@example.com",
        "first.last@example.com",
        "alerts@mail.example.org",
        "alerts_1@example-domain.com",
    ],
)
def test_email_address_validation_accepts_common_addresses(address):
    _validate_address(address, "ERROR_EMAIL_TO")
    _validate_address(address, "SMTP_FROM_EMAIL")


@pytest.mark.parametrize(
    "address",
    [
        "alerts@exa$mple.com",
        "alerts@example!.com",
        "alerts@exa_mple.com",
        "alerts..test@example.com",
        ".alerts@example.com",
        "alerts.@example.com",
        "alerts@example",
        "alerts@example..com",
        "alerts@.example.com",
        "alerts@example.com.",
        "alerts@-example.com",
        "alerts@example-.com",
        "alerts @example.com",
        "alerts@example .com",
        "alerts@@example.com",
        "",
        "alerts@example.com\x00",
        f"{'a' * 65}@example.com",
        f"alerts@{'a' * 64}.example.com",
        f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 63}.com",
    ],
)
def test_email_address_validation_rejects_invalid_addresses(address):
    with pytest.raises(ErrorEmailConfigurationError, match="ERROR_EMAIL_TO"):
        _validate_address(address, "ERROR_EMAIL_TO")
    with pytest.raises(ErrorEmailConfigurationError, match="SMTP_FROM_EMAIL"):
        _validate_address(address, "SMTP_FROM_EMAIL")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"error_email_to": "not-an-address"}, "ERROR_EMAIL_TO"),
        ({"error_email_to": "alert@invalid"}, "ERROR_EMAIL_TO"),
        ({"smtp_host": None}, "SMTP_HOST"),
        ({"smtp_from_email": None}, "SMTP_FROM_EMAIL"),
        ({"smtp_port": 0}, "SMTP_PORT"),
        ({"smtp_port": 65536}, "SMTP_PORT"),
        ({"smtp_username": "sender@example.com", "smtp_password": None}, "SMTP_USERNAME"),
        ({"smtp_username": None, "smtp_password": "smtp-secret-password"}, "SMTP_USERNAME"),
        ({"smtp_starttls": True, "smtp_use_ssl": True}, "нельзя включать"),
        ({"smtp_starttls": False, "smtp_use_ssl": False}, "включите"),
    ],
)
def test_invalid_alert_configuration_fails_without_revealing_password(
    overrides,
    message,
):
    with pytest.raises(ErrorEmailConfigurationError, match=message) as exc_info:
        validate_error_email_settings(make_settings(**overrides))

    assert "smtp-secret-password" not in str(exc_info.value)


@pytest.mark.parametrize("level", [logging.ERROR, logging.CRITICAL])
def test_error_and_critical_records_are_queued(level):
    handler = make_handler()

    handler.emit(make_record(level=level))

    assert handler.pending_notifications == 1


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING])
def test_lower_levels_are_ignored(level):
    handler = make_handler()

    handler.emit(make_record(level=level))

    assert handler.pending_notifications == 0


def test_identical_fingerprint_is_suppressed_and_suppression_does_not_extend_cooldown():
    now = [100.0]
    handler = make_handler(clock=lambda: now[0])
    record = make_record(message="same   error\nmessage")

    handler.emit(record)
    now[0] += ERROR_EMAIL_COOLDOWN_SECONDS - 1
    handler.emit(make_record(message="same error message"))
    now[0] = 100.0 + ERROR_EMAIL_COOLDOWN_SECONDS
    handler.emit(make_record(message="same error message"))

    assert handler.pending_notifications == 2


def test_distinct_fingerprints_and_message_normalization():
    now = [0.0]
    handler = make_handler(clock=lambda: now[0])
    handler.emit(make_record(message="e\u0301chec   de\nservice"))
    handler.emit(make_record(message="échec de service"))
    handler.emit(make_record(message="Échec de service"))
    handler.emit(make_record(message="Échec de service!"))

    assert handler.pending_notifications == 3


def test_exception_type_participates_in_fingerprint():
    handler = make_handler()
    try:
        raise ValueError("private detail")
    except ValueError:
        value_error = __import__("sys").exc_info()
    try:
        raise TypeError("private detail")
    except TypeError:
        type_error = __import__("sys").exc_info()

    handler.emit(make_record(message="failed", exc_info=value_error))
    handler.emit(make_record(message="failed", exc_info=type_error))

    assert handler.pending_notifications == 2


def test_queue_overflow_is_nonblocking_and_does_not_start_cooldown():
    handler = make_handler(queue_size=1)
    assert handler._queue.maxsize == 1
    handler.emit(make_record(message="first"))
    handler.emit(make_record(message="dropped"))

    assert handler.pending_notifications == 1
    assert handler.dropped_notifications == 1

    handler._queue.get_nowait()
    handler._queue.task_done()
    handler.emit(make_record(message="dropped"))
    assert handler.pending_notifications == 1


def test_stale_fingerprints_are_pruned_and_storage_is_bounded():
    now = [0.0]
    handler = make_handler(clock=lambda: now[0])
    handler.emit(make_record(message="old"))
    now[0] = ERROR_EMAIL_COOLDOWN_SECONDS
    handler.emit(make_record(message="new"))
    assert len(handler._fingerprints) == 1
    assert next(iter(handler._fingerprints.values())) == now[0]


def test_email_payload_contains_only_allowlisted_values():
    handler = make_handler()
    token = set_request_context("request-123")
    bind_user_id("private-user-id")
    try:
        try:
            raise RuntimeError("secret password and token in exception")
        except RuntimeError:
            notification, _ = handler._make_notification(
                make_record(
                    message="request body and cookie must stay private",
                    exc_info=__import__("sys").exc_info(),
                )
            )
    finally:
        reset_request_context(token)

    subject, body = handler._format_email(notification)
    payload = subject + body
    assert notification.timestamp.endswith("Z")
    assert notification.level == "ERROR"
    assert notification.component == "app.example"
    assert notification.request_id == "request-123"
    assert notification.exception_type == "RuntimeError"
    for forbidden in (
        "private-user-id",
        "secret password",
        "request body",
        "cookie",
        "Traceback",
        "secret/path.py",
        "smtp-secret-password",
    ):
        assert forbidden not in payload
    assert "request-123" in payload
    assert "RuntimeError" in payload


@pytest.mark.asyncio
async def test_worker_uses_sender_on_its_own_event_loop_and_stops():
    main_loop = asyncio.get_running_loop()
    sent = threading.Event()
    sender_threads = []
    sender_loops = []

    async def deliver(**kwargs):
        sender_threads.append(threading.current_thread())
        sender_loops.append(asyncio.get_running_loop())
        sent.set()

    sender = FakeSender(deliver)
    handler = make_handler(sender=sender)
    handler.start()
    handler.emit(make_record())

    assert await asyncio.to_thread(sent.wait, 2)
    await handler.stop()

    assert len(sender.calls) == 1
    assert sender_threads[0] is not threading.current_thread()
    assert sender_loops[0] is not main_loop


@pytest.mark.asyncio
async def test_shutdown_drains_pending_queue_within_deadline():
    sent_messages = []

    async def deliver(**kwargs):
        sent_messages.append(kwargs)

    handler = make_handler(sender=FakeSender(deliver))
    handler.start()
    handler.emit(make_record(message="first"))
    handler.emit(make_record(message="second"))
    await handler.stop()

    assert len(sent_messages) == 2
    assert handler.pending_notifications == 0


@pytest.mark.asyncio
async def test_smtp_failure_does_not_recurse_into_alert_queue(caplog):
    finished = threading.Event()

    async def fail_delivery(**kwargs):
        finished.set()
        raise RuntimeError("smtp credential should not be logged")

    handler = make_handler(sender=FakeSender(fail_delivery))
    root = logging.getLogger()
    root.addHandler(handler)
    handler.start()
    try:
        root.error("initial failure")
        assert await asyncio.to_thread(finished.wait, 2)
        await asyncio.wait_for(asyncio.to_thread(handler._queue.join), timeout=2)
        assert handler.pending_notifications == 0
        assert handler.delivery_failures == 1
        assert "Error notification delivery failed (RuntimeError)" in caplog.text
        assert "smtp credential should not be logged" not in caplog.text
    finally:
        root.removeHandler(handler)
        await handler.stop()


@pytest.mark.asyncio
async def test_shutdown_wait_is_bounded_and_does_not_block_event_loop(monkeypatch):
    import app.infrastructure.emailing.error_notifications as notifications

    monkeypatch.setattr(notifications, "ERROR_EMAIL_SHUTDOWN_TIMEOUT_SECONDS", 0.05)
    started = threading.Event()

    async def slow_delivery(**kwargs):
        started.set()
        await asyncio.sleep(0.2)

    handler = make_handler(sender=FakeSender(slow_delivery))
    handler.start()
    handler.emit(make_record())
    assert await asyncio.to_thread(started.wait, 2)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.01)
            ticks += 1

    await asyncio.gather(handler.stop(), ticker())
    await asyncio.to_thread(handler._thread.join, 2)

    assert ticks == 5
    assert not handler._thread.is_alive()
