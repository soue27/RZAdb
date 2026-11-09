import asyncio
import json
import logging

import pytest

from app.core.logging_config import configure_logging
from app.core.request_context import (
    bind_user_id,
    get_request_context,
)
from app.presentation.middleware.request_context import RequestContextMiddleware


@pytest.fixture
def restore_logging_state():
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    logger_names = ("app", "uvicorn", "uvicorn.error", "uvicorn.access")
    loggers = {
        name: (
            logging.getLogger(name).level,
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            logging.getLogger(name).disabled,
        )
        for name in logger_names
    }
    streams = {
        handler: handler.stream
        for handler in handlers
        if isinstance(handler, logging.StreamHandler)
    }
    yield
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
        if getattr(handler, "_rzadb_json_stdout_handler", False) and handler not in handlers:
            handler.close()
    root.setLevel(level)
    for handler in handlers:
        if handler in streams:
            handler.stream = streams[handler]
        root.addHandler(handler)
    for name, state in loggers.items():
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(state[0])
        logger.propagate = state[2]
        logger.disabled = state[3]
        for handler in state[1]:
            logger.addHandler(handler)


def _scope(*, path="/probe", query_string=b"token=secret", headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }


async def _invoke(app, *, scope=None):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope or _scope(), receive, send)
    return messages


@pytest.mark.asyncio
async def test_request_id_is_generated_and_returned_without_dropping_headers(
    capsys,
    restore_logging_state,
):
    configure_logging("INFO")
    observed = []

    async def endpoint(scope, receive, send):
        observed.append(get_request_context().request_id)
        await send(
            {
                "type": "http.response.start",
                "status": 302,
                "headers": [(b"location", b"/next"), (b"x-existing", b"kept")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestContextMiddleware(endpoint)
    first = await _invoke(
        middleware,
        scope=_scope(headers=[(b"x-request-id", b"attacker-value")]),
    )
    second = await _invoke(middleware)

    first_headers = dict(first[0]["headers"])
    assert first_headers[b"location"] == b"/next"
    assert first_headers[b"x-existing"] == b"kept"
    assert first_headers[b"x-request-id"].decode() == observed[0]
    assert first_headers[b"x-request-id"] != b"attacker-value"
    assert dict(second[0]["headers"])[b"x-request-id"].decode() == observed[1]
    assert observed[0] != observed[1]
    assert get_request_context() is None

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    completed = events[0]
    assert completed["message"] == "http.request.completed"
    assert completed["request_id"] == observed[0]
    assert completed["method"] == "GET"
    assert completed["path"] == "/probe"
    assert completed["status_code"] == 302
    assert completed["duration_ms"] >= 0
    assert "query_string" not in completed
    assert "secret" not in json.dumps(completed)


@pytest.mark.asyncio
async def test_exception_logs_safe_failure_and_resets_context(
    capsys,
    restore_logging_state,
):
    configure_logging("INFO")
    original_error = RuntimeError("private diagnostic")

    async def endpoint(scope, receive, send):
        raise original_error

    with pytest.raises(RuntimeError) as raised:
        await _invoke(RequestContextMiddleware(endpoint))

    assert raised.value is original_error
    assert get_request_context() is None
    output = capsys.readouterr().out
    assert "private diagnostic" not in output
    failure = json.loads(output)
    assert failure["message"] == "http.request.failed"
    assert failure["status_code"] == 500
    assert failure["path"] == "/probe"
    assert "exception" not in failure


@pytest.mark.asyncio
async def test_cancellation_resets_context_without_logging_failure(
    capsys,
    restore_logging_state,
):
    configure_logging("INFO")

    async def endpoint(scope, receive, send):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _invoke(RequestContextMiddleware(endpoint))

    assert get_request_context() is None
    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
async def test_parallel_requests_keep_request_and_user_context_isolated(
    capsys,
    restore_logging_state,
):
    configure_logging("INFO")
    observed = []

    async def endpoint(scope, receive, send):
        bind_user_id(scope["user_id"])
        await asyncio.sleep(0)
        context = get_request_context()
        observed.append((scope["user_id"], context.request_id, context.user_id))
        logging.getLogger("app.http.test").info("isolated")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestContextMiddleware(endpoint)

    async def request(user_id):
        scope = _scope()
        scope["user_id"] = user_id
        await _invoke(middleware, scope=scope)

    await asyncio.gather(request("user-a"), request("user-b"))

    assert len({request_id for _, request_id, _ in observed}) == 2
    assert all(user_id == bound_user_id for user_id, _, bound_user_id in observed)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    isolated = [event for event in events if event["message"] == "isolated"]
    assert {(event["request_id"], event["user_id"]) for event in isolated} == {
        (request_id, user_id) for user_id, request_id, _ in observed
    }
