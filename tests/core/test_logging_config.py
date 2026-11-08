import json
import logging
from datetime import UTC, datetime

import pytest
import uvicorn

from app.core.logging_config import configure_logging


_LOGGER_NAMES = ("app", "uvicorn", "uvicorn.error", "uvicorn.access")
_HANDLER_MARKER = "_rzadb_json_stdout_handler"


@pytest.fixture
def restore_logging_state():
    root = logging.getLogger()
    original_root = (root.level, list(root.handlers))
    original_streams = {
        handler: handler.stream
        for handler in original_root[1]
        if isinstance(handler, logging.StreamHandler)
    }
    original_loggers = {}
    for name in _LOGGER_NAMES:
        logger = logging.getLogger(name)
        original_loggers[name] = (
            logger.level,
            list(logger.handlers),
            logger.propagate,
            logger.disabled,
        )

    yield

    for handler in tuple(root.handlers):
        root.removeHandler(handler)
        if (
            getattr(handler, _HANDLER_MARKER, False)
            and handler not in original_root[1]
        ):
            handler.close()
    root.setLevel(original_root[0])
    for handler in original_root[1]:
        if handler in original_streams:
            handler.stream = original_streams[handler]
        root.addHandler(handler)

    for name, state in original_loggers.items():
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(state[0])
        logger.propagate = state[2]
        logger.disabled = state[3]
        for handler in state[1]:
            logger.addHandler(handler)


def _records(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines()]


def test_json_formatter_writes_required_fields_and_utc_timestamp(
    capsys,
    restore_logging_state,
) -> None:
    configure_logging("INFO")

    logging.getLogger("app.logging_test").info("Пример сообщения")

    output = capsys.readouterr().out
    assert output.count("\n") == 1
    record = _records(output)[0]
    assert record["level"] == "INFO"
    assert record["logger"] == "app.logging_test"
    assert record["message"] == "Пример сообщения"
    timestamp = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    ("level", "method"),
    [
        ("DEBUG", "debug"),
        ("INFO", "info"),
        ("WARNING", "warning"),
        ("ERROR", "error"),
        ("CRITICAL", "critical"),
    ],
)
def test_all_supported_levels_are_formatted(
    capsys,
    restore_logging_state,
    level: str,
    method: str,
) -> None:
    configure_logging("DEBUG")

    getattr(logging.getLogger("app.logging_test"), method)("level message")

    record = _records(capsys.readouterr().out)[0]
    assert record["level"] == level


def test_json_escapes_multiline_unicode_and_ignores_extra_objects(
    capsys,
    restore_logging_state,
) -> None:
    configure_logging("INFO")

    logging.getLogger("app.logging_test").info(
        'Кавычки " и строка\nвторая',
        extra={"unserializable": object()},
    )

    output = capsys.readouterr().out
    assert output.count("\n") == 1
    record = _records(output)[0]
    assert record["message"] == 'Кавычки " и строка\nвторая'
    assert "unserializable" not in record


def test_exception_contains_type_and_full_traceback(
    capsys,
    restore_logging_state,
) -> None:
    configure_logging("ERROR")
    try:
        raise ValueError("ошибка с \"кавычками\"")
    except ValueError:
        logging.getLogger("app.logging_test").exception("Сбой операции")

    output = capsys.readouterr().out
    assert output.count("\n") == 1
    record = _records(output)[0]
    exception = record["exception"]
    assert exception["type"] == "ValueError"
    assert "Traceback (most recent call last)" in exception["traceback"]
    assert 'ValueError: ошибка с "кавычками"' in exception["traceback"]


def test_repeated_configuration_keeps_one_stdout_handler_and_one_record(
    capsys,
    restore_logging_state,
) -> None:
    configure_logging("INFO")
    configure_logging("INFO")

    root_handlers = logging.getLogger().handlers
    marked_handlers = [
        handler
        for handler in root_handlers
        if getattr(handler, _HANDLER_MARKER, False)
    ]
    assert len(marked_handlers) == 1

    logging.getLogger("app.logging_test").info("single")
    assert len(_records(capsys.readouterr().out)) == 1


def test_web_logging_has_no_file_handlers_and_uses_stdout(
    capsys,
    restore_logging_state,
) -> None:
    configure_logging("INFO")
    root_handlers = logging.getLogger().handlers

    assert len(root_handlers) == 1
    assert isinstance(root_handlers[0], logging.StreamHandler)
    assert not isinstance(root_handlers[0], logging.FileHandler)

    logging.getLogger("app.logging_test").info("stdout only")
    assert _records(capsys.readouterr().out)[0]["message"] == "stdout only"


def test_uvicorn_configure_order_routes_error_to_json_and_disables_access(
    capsys,
    restore_logging_state,
) -> None:
    # Mirrors Uvicorn's configure_logging-before-import-string startup order.
    uvicorn.Config("app.presentation.app:app").configure_logging()
    configure_logging("INFO")

    logging.getLogger("uvicorn.error").error("server error")
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.disabled is True
    access_logger.info("access request")

    output = capsys.readouterr().out
    records = _records(output)
    assert len(records) == 1
    assert records[0]["logger"] == "uvicorn.error"
    assert records[0]["message"] == "server error"
