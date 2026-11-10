"""app: создание и настройка FastAPI-приложения."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.infrastructure.database import models  # noqa: F401
from app.infrastructure.emailing.error_notifications import (
    acquire_error_email_handler,
    release_error_email_handler,
)
from app.presentation.auth.dependencies import PasswordChangeRequired
from app.presentation.middleware.request_context import RequestContextMiddleware
from app.presentation.routes.admin import router as admin_router
from app.presentation.routes.archive import router as archive_router
from app.presentation.routes.auth import router as auth_router
from app.presentation.routes.equipment_import import (
    router as equipment_import_router,
)
from app.presentation.routes.feedback import router as feedback_router
from app.presentation.routes.files import router as files_router
from app.presentation.routes.health import router as health_router
from app.presentation.routes.home import router as home_router
from app.presentation.routes.inspection_tasks import router as inspection_tasks_router
from app.presentation.routes.maintenance import (
    router as maintenance_router,
)
from app.presentation.routes.notifications import router as notifications_router
from app.presentation.routes.objects import router as objects_router
from app.presentation.routes.organization_import import (
    router as organization_import_router,
)
from app.presentation.routes.otd import router as otd_router
from app.presentation.routes.physical_deletions import (
    router as physical_deletions_router,
)
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


def _is_api_request(request: Request) -> bool:
    """Определяет, относится ли HTTP-запрос к API по пути или заголовкам клиента.
    """
    route = request.scope.get("route")
    if getattr(route, "response_model", None) is not None:
        return True

    path = request.url.path
    return path == "/files" or path.startswith("/files/")


async def _handle_auth_http_exception(
    request: Request,
    exc: HTTPException,
) -> Response:
    """Преобразует HTTP-ошибки аутентификации в подходящий ответ для API или HTML-интерфейса.

    Args:
        request: Текущий HTTP-запрос.
        exc: Исключение FastAPI.

    Returns:
        Ответ с кодом и содержимым, соответствующим типу клиента.
    """
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
    """Создаёт и настраивает экземпляр FastAPI.

    Регистрирует middleware, обработчики исключений, статические файлы,
    шаблоны и маршруты приложения.

    Returns:
        Настроенный экземпляр FastAPI.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        error_email_handler = acquire_error_email_handler(settings)
        app.state.error_email_handler = error_email_handler
        try:
            yield
        finally:
            await release_error_email_handler(error_email_handler)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
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
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )
    # Starlette inserts each newly-added middleware at the front of the stack.
    # This keeps request context available while SessionMiddleware runs.
    app.add_middleware(RequestContextMiddleware)

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
    app.include_router(physical_deletions_router)
    app.include_router(feedback_router)
    app.include_router(equipment_import_router)
    app.include_router(organization_import_router)

    return app


app = create_app()
