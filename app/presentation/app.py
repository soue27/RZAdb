from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.presentation.routes.auth import router as auth_router
from app.presentation.routes.files import router as files_router
from app.presentation.routes.health import router as health_router
from app.presentation.routes.home import router as home_router
from app.presentation.routes.users import router as users_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    app.mount(
        "/static",
        StaticFiles(directory="app/presentation/static"),
        name="static",
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=False,
        same_site="lax",
    )

    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(files_router)
    app.include_router(auth_router)
    app.include_router(home_router)


    return app


app = create_app()