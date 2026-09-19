from typing import Annotated

from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.application.files.service import FileService
from app.core.config import get_settings
from app.presentation.dependencies import get_file_service
from app.presentation.routes.files import router as files_router


def create_app() -> FastAPI:
    app = FastAPI(title="RZAdb")

    app.add_middleware(
        SessionMiddleware,
        secret_key=get_settings().session_secret,
        https_only=False,
        same_site="lax",
    )

    app.include_router(files_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/di-check")
    async def di_check(
        file_service: Annotated[FileService, Depends(get_file_service)],
    ) -> dict[str, str]:
        return {"status": "ok", "service": type(file_service).__name__}

    return app


app = create_app()