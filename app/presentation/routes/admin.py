"""Маршруты административной панели, управления пользователями и запуска резервного копирования."""

import asyncio
import contextvars
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.enterprises.repository import EnterpriseRepository
from app.application.users.repository import UserRepository
from app.application.users.service import UserOperationError, UserService
from app.core.config import Settings, get_settings
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.infrastructure.backup.coordinator import (
    BackupCoordinator,
    BackupDisabledError,
    BackupError,
    BackupManifestError,
)
from app.infrastructure.backup.run_lock import BackupAlreadyRunning, BackupRunLock
from app.infrastructure.database.session import get_session
from app.presentation.auth.dependencies import require_superadmin
from app.presentation.dependencies.services import get_user_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)
logger = logging.getLogger(__name__)

_BACKUP_STATUS_FILENAME = ".admin-backup-status.json"
_CHANNEL_NAMES = ("local", "email", "yandex_disk")
_BACKUP_STATUSES = {
    "idle",
    "running",
    "success",
    "partial_success",
    "failed",
    "pending",
    "disabled",
    "not_attempted",
}
_SAFE_BACKUP_ERRORS = {
    "Резервное копирование отключено настройкой BACKUP_ENABLED.",
    "Не удалось сохранить манифест резервной копии.",
    "Резервное копирование завершилось ошибкой.",
    "Внутренняя ошибка резервного копирования.",
    "Не удалось создать или проверить дамп. Подробности доступны в журнале приложения.",
    "Процесс резервного копирования был прерван.",
    "Резервное копирование уже выполняется.",
    "Не удалось запустить резервное копирование.",
    "Не удалось прочитать состояние резервного копирования.",
}


def _backup_status_path(settings: Settings) -> Path:
    return settings.backup_local_dir / _BACKUP_STATUS_FILENAME


def _write_backup_status(settings: Settings, state: dict[str, Any]) -> None:
    path = _backup_status_path(settings)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".admin-backup-status.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            json.dump(state, temporary, ensure_ascii=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_channel_error(name: str, error: object) -> str | None:
    if not error:
        return None
    message = str(error)
    if name == "email":
        if "BACKUP_EMAIL_TO" in message:
            return "Не настроен адрес получателя резервной копии."
        return "Ошибка отправки резервной копии по электронной почте."
    if name == "yandex_disk":
        if "BACKUP_YANDEX_DISK_TOKEN" in message:
            return "Не настроен токен Яндекс Диска."
        return "Ошибка загрузки резервной копии на Яндекс Диск."
    return "Ошибка сохранения резервной копии локально."


def _public_backup_state(result: dict[str, Any]) -> dict[str, Any]:
    channels = {}
    for name in _CHANNEL_NAMES:
        channel = result.get("channels", {}).get(name, {})
        channels[name] = {
            "enabled": bool(channel.get("enabled", False)),
            "status": channel.get("status", "unknown"),
            "error": _safe_channel_error(name, channel.get("error")),
            "retention_status": channel.get("retention_status"),
            "retention_error": (
                _safe_channel_error(name, channel.get("retention_error"))
                if channel.get("retention_error")
                else None
            ),
        }
    result_status = result.get("status", "failed")
    return {
        "run_id": result.get("run_id"),
        "status": result_status,
        "started_at": result.get("started_at"),
        "duration_seconds": result.get("duration_seconds"),
        "size_bytes": result.get("size_bytes"),
        "sha256": result.get("sha256"),
        "channels": channels,
        "error": (
            "Не удалось создать или проверить дамп. Подробности доступны в журнале приложения."
            if result_status == "failed"
            else None
        ),
    }


def _idle_backup_state(settings: Settings) -> dict[str, Any]:
    return {
        "run_id": None,
        "status": "idle",
        "started_at": None,
        "duration_seconds": None,
        "size_bytes": None,
        "sha256": None,
        "channels": {
            name: {
                "enabled": bool(getattr(settings, f"backup_{name}_enabled")),
                "status": "pending"
                if getattr(settings, f"backup_{name}_enabled")
                else "disabled",
                "error": None,
                "retention_status": None,
                "retention_error": None,
            }
            for name in _CHANNEL_NAMES
        },
        "error": None,
    }


def _read_backup_status(settings: Settings) -> dict[str, Any]:
    path = _backup_status_path(settings)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("status must be an object")
    except FileNotFoundError:
        return _idle_backup_state(settings)
    except (OSError, ValueError, TypeError):
        logger.warning("Could not read admin backup status")
        state = _idle_backup_state(settings)
        state["status"] = "failed"
        state["error"] = "Не удалось прочитать состояние резервного копирования."
        return state

    # A persisted running state with an available lock means its worker exited.
    if state.get("status") == "running":
        lock = BackupRunLock(settings.backup_local_dir)
        try:
            lock.acquire()
        except BackupAlreadyRunning:
            pass
        else:
            try:
                try:
                    latest_state = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(latest_state, dict):
                        raise ValueError("status must be an object")
                except (OSError, ValueError, TypeError):
                    logger.warning("Could not reread admin backup status under lock")
                else:
                    state = latest_state
                    if state.get("status") == "running":
                        state["status"] = "failed"
                        state["error"] = "Процесс резервного копирования был прерван."
                        try:
                            _write_backup_status(settings, state)
                        except OSError:
                            logger.warning("Could not persist interrupted backup status")
            finally:
                lock.release()
    return _sanitize_backup_state(state)


def _sanitize_backup_state(state: dict[str, Any]) -> dict[str, Any]:
    raw_channels = state.get("channels")
    if not isinstance(raw_channels, dict):
        raw_channels = {}
    channels = {}
    for name in _CHANNEL_NAMES:
        channel = raw_channels.get(name)
        if not isinstance(channel, dict):
            channel = {}
        channel_status = channel.get("status")
        if channel_status not in _BACKUP_STATUSES:
            channel_status = "failed"
        channels[name] = {
            "enabled": bool(channel.get("enabled", False)),
            "status": channel_status,
            "error": _safe_channel_error(name, channel.get("error")),
            "retention_status": (
                channel.get("retention_status")
                if channel.get("retention_status") in _BACKUP_STATUSES
                else None
            ),
            "retention_error": (
                _safe_channel_error(name, channel.get("retention_error"))
                if channel.get("retention_error")
                else None
            ),
        }
    result_status = state.get("status")
    if result_status not in _BACKUP_STATUSES:
        result_status = "failed"
    error = state.get("error")
    if error and error not in _SAFE_BACKUP_ERRORS:
        error = "Не удалось выполнить резервное копирование."
    return {
        "run_id": state.get("run_id") if result_status != "idle" else None,
        "status": result_status,
        "started_at": state.get("started_at"),
        "duration_seconds": state.get("duration_seconds"),
        "size_bytes": state.get("size_bytes"),
        "sha256": state.get("sha256"),
        "channels": channels,
        "error": error,
    }


def _render_backup_status(
    request: Request, state: dict[str, Any], *, backup_enabled: bool
) -> Response:
    state = _sanitize_backup_state(state)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="admin/_backup_status.html",
            context={"backup": state, "backup_enabled": backup_enabled},
        )
    return JSONResponse(state)


def _run_backup_in_thread(settings: Settings, lock: BackupRunLock) -> None:
    try:
        try:
            result = asyncio.run(BackupCoordinator(settings).run())
            state = _public_backup_state(result)
        except BackupDisabledError:
            state = _idle_backup_state(settings)
            state.update(
                {
                    "status": "failed",
                    "error": "Резервное копирование отключено настройкой BACKUP_ENABLED.",
                }
            )
        except BackupManifestError:
            state = _idle_backup_state(settings)
            state.update(
                {
                    "status": "failed",
                    "error": "Не удалось сохранить манифест резервной копии.",
                }
            )
        except BackupError:
            state = _idle_backup_state(settings)
            state.update(
                {"status": "failed", "error": "Резервное копирование завершилось ошибкой."}
            )
        except Exception as exc:
            logger.exception(
                "Unexpected admin backup failure (%s)", type(exc).__name__
            )
            state = _idle_backup_state(settings)
            state.update(
                {"status": "failed", "error": "Внутренняя ошибка резервного копирования."}
            )
        try:
            _write_backup_status(settings, state)
        except OSError as exc:
            logger.error("Could not persist admin backup status (%s)", type(exc).__name__)
    finally:
        lock.release()


def _backup_status_response(
    request: Request, state: dict[str, Any], settings: Settings
) -> Response:
    return _render_backup_status(
        request,
        state,
        backup_enabled=settings.backup_enabled,
    )


def _role_labels() -> dict[str, str]:
    return {
        "superadmin": "Суперпользователь",
        "admin": "Администратор",
        "specialist": "Специалист",
        "manager": "Руководитель",
        "engineer": "Инженер",
    }


async def _user_form(request, session, current_user, *, user=None, error=None, values=None):
    enterprises = await EnterpriseRepository(session).get_all_for_access_scope()
    return templates.TemplateResponse(
        request=request,
        name="admin/user_form.html",
        context={
            "current_user": current_user,
            "user": user,
            "roles": list(UserRole),
            "role_labels": _role_labels(),
            "categories": list(AccessCategory),
            "enterprises": enterprises,
            "error": error,
            "values": values or {},
        },
        status_code=400 if error else 200,
    )



@router.get("/")
async def admin_dashboard(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    role_filter: str | None = None,
    status_filter: str | None = None,
    enterprise_filter: str | None = None,
):
    """Отображает административную панель и список пользователей.
    """
    settings = get_settings()

    allowed_statuses = {"active", "inactive", "archived"}
    status_filter = status_filter or None

    if status_filter is not None and status_filter not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Неизвестный статус пользователя.",
        )

    role_filter = role_filter or None

    if role_filter is not None:
        try:
            role_filter = UserRole(role_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Неизвестная роль пользователя.",
            ) from exc

    enterprise_filter = enterprise_filter or None
    without_enterprise = enterprise_filter == "none"
    enterprise_id = None

    if enterprise_filter is not None and not without_enterprise:
        try:
            enterprise_id = UUID(enterprise_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Некорректный идентификатор предприятия.",
            ) from exc

    enterprise_repository = EnterpriseRepository(session)
    enterprises = await enterprise_repository.get_all_for_access_scope()

    users = await UserRepository(session).get_all(
        role=role_filter,
        status_filter=status_filter,
        enterprise_id=enterprise_id,
        without_enterprise=without_enterprise,
    )

    role_labels = _role_labels()

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={
            "current_user": current_user,
            "users": users,
            "role_filter": role_filter,
            "status_filter": status_filter,
            "roles": list(UserRole),
            "role_labels": role_labels,
            "enterprises": enterprises,
            "enterprise_filter": enterprise_filter,
            "backup_status": _read_backup_status(settings),
            "backup_enabled": settings.backup_enabled,
        },
    )


@router.post("/backup")
async def start_admin_backup(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
):
    """Запускает резервное копирование PostgreSQL в фоновом потоке.

    Возвращает текущий статус запуска; длительная операция не выполняется
    непосредственно внутри HTTP-запроса.
    """
    settings = get_settings()
    lock = BackupRunLock(settings.backup_local_dir)
    try:
        lock.acquire()
    except BackupAlreadyRunning:
        state = _read_backup_status(settings)
        state["status"] = "running"
        state["error"] = "Резервное копирование уже выполняется."
        if request.headers.get("HX-Request") == "true":
            return _backup_status_response(request, state, settings)
        return JSONResponse(state, status_code=status.HTTP_409_CONFLICT)
    except OSError as exc:
        logger.error("Could not acquire admin backup lock (%s)", type(exc).__name__)
        state = _idle_backup_state(settings)
        state.update(
            {
                "status": "failed",
                "error": "Не удалось запустить резервное копирование.",
            }
        )
        return _backup_status_response(request, state, settings)

    state = _idle_backup_state(settings)
    state.update(
        {
            "run_id": None,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
    )
    try:
        _write_backup_status(settings, state)
        thread = threading.Thread(
            target=contextvars.Context().run,
            args=(_run_backup_in_thread, settings, lock),
            name="admin-postgres-backup",
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        lock.release()
        logger.error("Could not start admin backup worker (%s)", type(exc).__name__)
        state.update(
            {"status": "failed", "error": "Не удалось запустить резервное копирование."}
        )
        try:
            _write_backup_status(settings, state)
        except OSError:
            logger.warning("Could not persist failed admin backup status")
    return _backup_status_response(request, state, settings)


@router.get("/backup/status")
async def admin_backup_status(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
):
    """Возвращает актуальное состояние резервного копирования для административного интерфейса.
    """
    settings = get_settings()
    return _backup_status_response(request, _read_backup_status(settings), settings)


@router.get("/users/new")
async def new_user_page(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Отображает форму создания новой учётной записи.
    """
    return await _user_form(request, session, current_user)


@router.post("/users")
async def create_user(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[UserService, Depends(get_user_service)],
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    role: Annotated[UserRole, Form()],
    access_category: Annotated[AccessCategory, Form()],
    temporary_password: Annotated[str, Form()],
    enterprise_id: Annotated[str, Form()] = "",
):
    """Создаёт пользователя по данным административной формы.

    Проверяет входные поля через UserService и возвращает форму с ошибкой
    либо перенаправляет к списку пользователей.
    """
    try:
        await service.create(
            actor=current_user,
            full_name=full_name,
            email=email,
            role=role,
            enterprise_id=UUID(enterprise_id) if enterprise_id else None,
            access_category=access_category,
            temporary_password=temporary_password,
        )
    except (UserOperationError, ValueError) as exc:
        return await _user_form(
            request,
            session,
            current_user,
            error=str(exc),
            values={
                "full_name": full_name,
                "email": email,
                "role": role.value,
                "access_category": access_category.value,
                "enterprise_id": enterprise_id,
            },
        )
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/users/{user_id}")
async def edit_user_page(
    request: Request,
    user_id: UUID,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Отображает форму редактирования выбранной учётной записи.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Редактирование своего профиля запрещено.")
    user = await UserRepository(session).get_managed_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    return await _user_form(request, session, current_user, user=user)


@router.post("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: UUID,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[UserService, Depends(get_user_service)],
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    role: Annotated[UserRole, Form()],
    access_category: Annotated[AccessCategory, Form()],
    enterprise_id: Annotated[str, Form()] = "",
):
    """Обновляет основные сведения и область ответственности пользователя.
    """
    user = await UserRepository(session).get_managed_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    try:
        await service.update(
            actor=current_user,
            user_id=user_id,
            full_name=full_name,
            email=email,
            role=role,
            enterprise_id=UUID(enterprise_id) if enterprise_id else None,
            access_category=access_category,
        )
    except (UserOperationError, ValueError) as exc:
        return await _user_form(
            request,
            session,
            current_user,
            user=user,
            error=str(exc),
            values={
                "full_name": full_name,
                "email": email,
                "role": role.value,
                "access_category": access_category.value,
                "enterprise_id": enterprise_id,
            },
        )
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/password")
async def reset_user_password(
    user_id: UUID,
    current_user: Annotated[User, Depends(require_superadmin)],
    service: Annotated[UserService, Depends(get_user_service)],
    temporary_password: Annotated[str, Form()],
):
    """Устанавливает пользователю временный пароль с обязательной сменой при входе.
    """
    try:
        await service.reset_password(
            actor=current_user,
            user_id=user_id,
            temporary_password=temporary_password,
        )
    except UserOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/active")
async def set_user_active(
    user_id: UUID,
    active: Annotated[bool, Form()],
    current_user: Annotated[User, Depends(require_superadmin)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """Включает или отключает учётную запись пользователя.
    """
    try:
        await service.set_active(actor=current_user, user_id=user_id, active=active)
    except UserOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/archive")
async def archive_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(require_superadmin)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """Архивирует учётную запись пользователя без физического удаления.
    """
    try:
        await service.archive(actor=current_user, user_id=user_id)
    except UserOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)

