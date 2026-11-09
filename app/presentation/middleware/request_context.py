"""request_context: контекст и логирование HTTP-запросов."""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uuid6 import uuid7

from app.core.request_context import reset_request_context, set_request_context


logger = logging.getLogger("app.http")


class RequestContextMiddleware:
    """ASGI middleware, создающий request_id, добавляющий его в ответ и журналирующий длительность HTTP-запроса.
    """
    def __init__(self, app: ASGIApp) -> None:
        """Сохраняет ASGI-приложение, которое будет обёрнуто middleware.

        Args:
            app: Следующее ASGI-приложение в цепочке.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Обрабатывает HTTP-запрос с контекстом request_id и структурированным логированием.

        Для не-HTTP scope передаёт управление приложению без дополнительной обработки.

        Args:
            scope: ASGI scope.
            receive: Канал получения ASGI-сообщений.
            send: Канал отправки ASGI-сообщений.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid7())
        token = set_request_context(request_id)
        started_at = time.perf_counter()
        status_code: int | None = None
        method = scope.get("method", "")
        path = scope.get("path", "")

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_message = dict(message)
                response_message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode("ascii")),
                ]
                await send(response_message)
                return
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.error(
                "http.request.failed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": _duration_ms(started_at),
                },
            )
            raise
        else:
            logger.info(
                "http.request.completed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code if status_code is not None else 500,
                    "duration_ms": _duration_ms(started_at),
                },
            )
        finally:
            reset_request_context(token)


def _duration_ms(started_at: float) -> float:
    """Возвращает длительность операции в миллисекундах с округлением до тысячных.

    Args:
        started_at: Значение time.perf_counter() в момент начала.

    Returns:
        Длительность в миллисекундах.
    """
    return round((time.perf_counter() - started_at) * 1000, 3)
