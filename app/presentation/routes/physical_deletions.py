"""Маршруты физического удаления документных записей через общий сервис."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError

from app.application.files.physical_deletion import PhysicalDeletionService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_physical_deletion_service

router = APIRouter(prefix="/objects", tags=["physical deletion"])


def _error_response(message: str, status_code: int):
    return JSONResponse(status_code=status_code, content={"detail": message})


async def _delete(
    request: Request,
    kind: str,
    record_id: UUID,
    user: User,
    service: PhysicalDeletionService,
):
    """Выполняет физическое удаление документной записи через общий сервис удаления.

    Args:
    kind: Ключ типа удаляемой записи.
    record_id: Идентификатор записи.
    user: Пользователь, выполняющий удаление.

    Returns:
    HTTP-ответ с результатом операции.
    """
    try:
        result = await service.delete(kind=kind, record_id=record_id, user_id=user.id)
    except PermissionError as exc:
        return _error_response(str(exc), 403)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except RuntimeError as exc:
        return _error_response(str(exc), 409)
    except IntegrityError:
        return _error_response(
            "Запись нельзя удалить: от неё зависят другие данные.",
            409,
        )
    if request.headers.get("HX-Request") != "true":
        substation_kinds = {"inspection", "rza_instruction_version", "selectivity_scheme_version"}
        page_tab = {
            "inspection": "inspections",
            "rza_instruction_version": "instructions",
            "selectivity_scheme_version": "selectivity-schemes",
            "otd_version": "otd",
            "settings": "settings",
            "schema": "schemas",
            "maintenance": "maintenance",
            "program": "programs",
            "urza_instruction_version": "instruction",
        }[kind]
        parent = "substation" if kind in substation_kinds else "urza"
        return RedirectResponse(
            f"/objects/{parent}/{result.owner_id}?tab={page_tab}", status_code=303
        )
    if result.file_cleanup_failed:
        return HTMLResponse(
            '<div id="htmx-error-message" hx-swap-oob="outerHTML" '
            'class="alert alert-warning alert-dismissible fade show" role="alert" '
            'aria-live="polite"><span id="htmx-error-text">Запись удалена, но '
            'не удалось удалить один из файлов. Обратитесь к администратору.'
            '</span><button type="button" class="btn-close" aria-label="Закрыть" '
            'onclick="this.parentElement.classList.add(\'d-none\')"></button></div>'
        )
    return Response(status_code=200)


def _endpoint(kind: str):
    """Создаёт обработчик маршрута физического удаления для заданного типа записи.

    Args:
    kind: Ключ типа удаления из конфигурации сервиса.

    Returns:
    Асинхронный endpoint, принимающий идентификатор записи.
    """
    async def endpoint(request: Request, record_id: UUID,
                       user: Annotated[User, Depends(get_current_user)],
                       service: Annotated[PhysicalDeletionService, Depends(get_physical_deletion_service)]):
        return await _delete(request, kind, record_id, user, service)
    return endpoint


router.add_api_route("/substation/inspections/{record_id}/delete", _endpoint("inspection"), methods=["POST"])
router.add_api_route("/substation/instructions/versions/{record_id}/delete", _endpoint("rza_instruction_version"), methods=["POST"])
router.add_api_route("/substation/selectivity-schemes/versions/{record_id}/delete", _endpoint("selectivity_scheme_version"), methods=["POST"])
router.add_api_route("/urza/otd/versions/{record_id}/delete", _endpoint("otd_version"), methods=["POST"])
router.add_api_route("/urza/settings/{record_id}/physical-delete", _endpoint("settings"), methods=["POST"])
router.add_api_route("/urza/schemas/{record_id}/physical-delete", _endpoint("schema"), methods=["POST"])
router.add_api_route("/urza/maintenance/{record_id}/physical-delete", _endpoint("maintenance"), methods=["POST"])
router.add_api_route("/urza/programs/{record_id}/physical-delete", _endpoint("program"), methods=["POST"])
router.add_api_route("/urza/instruction/versions/{record_id}/delete", _endpoint("urza_instruction_version"), methods=["POST"])
