from pathlib import Path

from fastapi.responses import FileResponse


class TemporaryFileResponse(FileResponse):
    """Delete a generated response file after send, including cancelled sends."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            Path(self.path).unlink(missing_ok=True)
