"""responses: HTTP-ответы для временных файлов."""

from pathlib import Path

from fastapi.responses import FileResponse


class TemporaryFileResponse(FileResponse):
    """Delete a generated response file after send, including cancelled sends."""

    async def __call__(self, scope, receive, send) -> None:
        """Передаёт файл клиенту и удаляет временный файл после завершения отправки.

        Args:
            scope: ASGI scope запроса.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        try:
            await super().__call__(scope, receive, send)
        finally:
            Path(self.path).unlink(missing_ok=True)
