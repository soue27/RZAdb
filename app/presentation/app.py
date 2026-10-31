from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.infrastructure.database import models  # noqa: F401
from app.presentation.auth.dependencies import PasswordChangeRequired
from app.presentation.routes.admin import router as admin_router
from app.presentation.routes.archive import router as archive_router
from app.presentation.routes.auth import router as auth_router
from app.presentation.routes.files import router as files_router
from app.presentation.routes.health import router as health_router
from app.presentation.routes.home import router as home_router
from app.presentation.routes.inspection_tasks import router as inspection_tasks_router
from app.presentation.routes.maintenance import (
    router as maintenance_router,
)
from app.presentation.routes.objects import router as objects_router
from app.presentation.routes.otd import router as otd_router
from app.presentation.routes.programs import router as programs_router
from app.presentation.routes.schemes import router as schemes_router
from app.presentation.routes.settings import router as settings_router
from app.presentation.routes.substation_documents import (
    router as substation_documents_router,
)
from app.presentation.routes.substation_tasks import router as substation_tasks_router
from app.presentation.routes.tasks import router as tasks_router
from app.presentation.routes.urza_instructions import router as urza_instructions_router
from app.presentation.routes.urza_objects import router as urza_objects_router
from app.presentation.routes.users import router as users_router
from app.presentation.routes.notifications import router as notifications_router


def _is_api_request(request: Request) -> bool:
    route = request.scope.get("route")
    if getattr(route, "response_model", None) is not None:
        return True

    path = request.url.path
    return path == "/files" or path.startswith("/files/")


async def _handle_auth_http_exception(
    request: Request,
    exc: HTTPException,
) -> Response:
    is_authentication_failure = exc.status_code == status.HTTP_401_UNAUTHORIZED
    is_password_change_required = isinstance(exc, PasswordChangeRequired)
    is_login_submission = request.url.path == "/auth/login"

    if (
        not _is_api_request(request)
        and not is_login_submission
        and (is_authentication_failure or is_password_change_required)
    ):
        destination = (
            "/auth/change-password"
            if is_password_change_required
            else "/auth/login"
        )
        response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
        if is_authentication_failure:
            request.session.clear()
            response.delete_cookie("session", httponly=True, samesite="lax")
        return response

    return await http_exception_handler(request, exc)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )
    app.add_exception_handler(HTTPException, _handle_auth_http_exception)

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
    app.include_router(objects_router)
    app.include_router(archive_router)
    app.include_router(urza_objects_router)
    app.include_router(substation_documents_router)
    app.include_router(substation_tasks_router)
    app.include_router(inspection_tasks_router)
    app.include_router(otd_router)
    app.include_router(maintenance_router)
    app.include_router(programs_router)
    app.include_router(urza_instructions_router)
    app.include_router(settings_router)
    app.include_router(schemes_router)
    app.include_router(tasks_router)
    app.include_router(admin_router)
    app.include_router(notifications_router)

    return app


app = create_app()
