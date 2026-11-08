import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any


_JSON_HANDLER_MARKER = "_rzadb_json_stdout_handler"
_SUPPORTED_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class JSONFormatter(logging.Formatter):
    """Format log records as one-line JSON objects with a stable field set."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        try:
            message = record.getMessage()
        except Exception as exc:
            message = f"<message formatting failed: {type(exc).__name__}>"

        payload: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            if exc_type is not None:
                try:
                    traceback_text = "".join(
                        traceback.format_exception(
                            exc_type,
                            exc_value,
                            exc_traceback,
                        )
                    ).rstrip()
                except Exception as exc:
                    traceback_text = (
                        f"<traceback formatting failed: {type(exc).__name__}>"
                    )
                payload["exception"] = {
                    "type": exc_type.__name__,
                    "traceback": traceback_text,
                }

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def configure_logging(level: str) -> None:
    """Configure web-process logging; CLI entrypoints keep their own setup."""
    normalized_level = level.strip().upper()
    if normalized_level not in _SUPPORTED_LEVELS:
        raise ValueError(
            "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
        )
    numeric_level = logging.getLevelName(normalized_level)

    root_logger = logging.getLogger()
    handler = next(
        (
            current
            for current in root_logger.handlers
            if getattr(current, _JSON_HANDLER_MARKER, False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        setattr(handler, _JSON_HANDLER_MARKER, True)

    for current in tuple(root_logger.handlers):
        if current is not handler:
            root_logger.removeHandler(current)
            current.close()
    if isinstance(handler, logging.StreamHandler) and handler.stream is not sys.stdout:
        handler.setStream(sys.stdout)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(JSONFormatter())
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.setLevel(numeric_level)
    app_logger.propagate = True
    app_logger.disabled = False

    for logger_name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(numeric_level)
        uvicorn_logger.propagate = True
        uvicorn_logger.disabled = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
