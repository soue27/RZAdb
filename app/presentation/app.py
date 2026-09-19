from typing import Annotated

from fastapi import Depends, FastAPI

from app.application.files.service import FileService
from app.presentation.dependencies import get_file_service


def create_app() -> FastAPI:
    app = FastAPI(
        title="RZAdb",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/di-check")
    async def di_check(
        file_service: Annotated[
            FileService,
            Depends(get_file_service),
        ],
    ) -> dict[str, str]:
        return {
            "status": "ok",
            "service": type(file_service).__name__,
        }

    return app


app = create_app()