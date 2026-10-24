from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.access.service import AccessService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.objects.archive_service import (
    ArchiveBlockedError,
    ArchiveObjectType,
    ArchivePreview,
    ArchiveService,
)
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.tasks.repository import TaskRepository
from app.domain.enums import TaskStatus
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_access_service,
    get_archive_service,
    get_inspection_task_repository,
    get_task_repository,
)

router = APIRouter(prefix="/objects", tags=["archive"])
templates = Jinja2Templates(directory="app/presentation/templates")

_OBJECT_LABELS = {
    "substation": "Подстанция",
    "connection": "Присоединение",
    "urza": "УРЗА",
}
_STATUS_LABELS = {
    TaskStatus.CREATED: "Создано",
    TaskStatus.ASSIGNED: "Назначено",
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.COMPLETED: "Выполнено",
    TaskStatus.UNDER_REVIEW: "На проверке",
    TaskStatus.CLOSED: "Закрыто",
    TaskStatus.REJECTED: "Отклонено",
}


def _object_type(value: str) -> ArchiveObjectType:
    if value not in _OBJECT_LABELS:
        raise HTTPException(status_code=404, detail="Тип объекта не найден.")
    return value  # type: ignore[return-value]


def _card_url(
    object_type: ArchiveObjectType, object_id: UUID, *, archived: bool
) -> str:
    suffix = "?archived=true" if archived else ""
    return f"/objects/{object_type}/{object_id}{suffix}"


async def _visible_blockers(
    preview: ArchivePreview,
    *,
    user: User,
    access_service: AccessService,
    task_repository: TaskRepository,
    inspection_repository: InspectionTaskRepository,
) -> list[dict[str, str]]:
    visible = []
    for blocker in preview.blockers:
        if blocker.process_type == "task":
            task = await task_repository.get_active_by_id(blocker.process_id)
            if task is None:
                continue
            has_access = (
                await access_service.can_access_urza(user.id, task.urza_id)
                if task.urza_id is not None
                else await access_service.can_access_substation(
                    user.id, task.substation_id
                )
            )
            if not has_access:
                continue
            if user.role.value == "engineer" and task.assigned_to != user.id:
                continue
            url = f"/tasks/{task.id}"
            label = "Задание"
        else:
            task = await inspection_repository.get_active_by_id(blocker.process_id)
            if task is None or not await access_service.can_access_substation(
                user.id, task.substation_id
            ):
                continue
            url = f"/objects/substation/inspection-tasks/{task.id}"
            label = "Осмотр"

        visible.append(
            {
                "process_type": blocker.process_type,
                "process_id": str(blocker.process_id),
                "status": _STATUS_LABELS[blocker.status],
                "label": label,
                "url": url,
            }
        )
    return visible


async def _preview_context(
    preview: ArchivePreview,
    *,
    user: User,
    access_service: AccessService,
    task_repository: TaskRepository,
    inspection_repository: InspectionTaskRepository,
) -> dict:
    blockers = await _visible_blockers(
        preview,
        user=user,
        access_service=access_service,
        task_repository=task_repository,
        inspection_repository=inspection_repository,
    )
    return {
        "object_type": preview.object_type,
        "object_id": preview.object_id,
        "objects": [
            {"type": kind, "label": _OBJECT_LABELS[kind], "id": object_id}
            for kind, object_id in preview.object_ids
        ],
        "blockers": blockers,
    }


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ObjectAccessDeniedError):
        raise HTTPException(
            status_code=403, detail="Доступ к объекту запрещён."
        ) from exc
    if isinstance(exc, ObjectNotFoundError):
        raise HTTPException(status_code=404, detail="Объект не найден.") from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _redirect(request: Request, url: str):
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{object_type}/{object_id}/archive/preview")
async def preview_archive(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    archive_service: Annotated[ArchiveService, Depends(get_archive_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    inspection_repository: Annotated[
        InspectionTaskRepository, Depends(get_inspection_task_repository)
    ],
):
    kind = _object_type(object_type)
    try:
        preview = await archive_service.preview(
            actor_id=current_user.id, object_type=kind, object_id=object_id
        )
    except (
        ObjectAccessDeniedError,
        ObjectNotFoundError,
        PermissionError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
    context = await _preview_context(
        preview,
        user=current_user,
        access_service=access_service,
        task_repository=task_repository,
        inspection_repository=inspection_repository,
    )
    return templates.TemplateResponse(
        request=request,
        name="objects/archive_preview.html",
        context=context,
    )


@router.post("/{object_type}/{object_id}/archive")
async def archive_object(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    archive_service: Annotated[ArchiveService, Depends(get_archive_service)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    inspection_repository: Annotated[
        InspectionTaskRepository, Depends(get_inspection_task_repository)
    ],
    reason: Annotated[str, Form()],
):
    kind = _object_type(object_type)
    try:
        await archive_service.archive(
            actor_id=current_user.id,
            object_type=kind,
            object_id=object_id,
            reason=reason,
        )
    except ArchiveBlockedError as exc:
        preview = ArchivePreview(kind, object_id, (), exc.blockers)
        context = await _preview_context(
            preview,
            user=current_user,
            access_service=access_service,
            task_repository=task_repository,
            inspection_repository=inspection_repository,
        )
        context.update(
            {
                "is_htmx": request.headers.get("HX-Request") == "true",
                "message": str(exc),
                "return_url": _card_url(kind, object_id, archived=False),
            }
        )
        return templates.TemplateResponse(
            request=request,
            name="objects/archive_conflict.html",
            context=context,
            status_code=status.HTTP_409_CONFLICT,
        )
    except (
        ObjectAccessDeniedError,
        ObjectNotFoundError,
        PermissionError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
    return _redirect(request, _card_url(kind, object_id, archived=True))


@router.post("/{object_type}/{object_id}/restore")
async def restore_object(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    archive_service: Annotated[ArchiveService, Depends(get_archive_service)],
    reason: Annotated[str | None, Form()] = None,
):
    kind = _object_type(object_type)
    try:
        await archive_service.restore(
            actor_id=current_user.id,
            object_type=kind,
            object_id=object_id,
            reason=reason,
        )
    except (
        ObjectAccessDeniedError,
        ObjectNotFoundError,
        PermissionError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
    return _redirect(request, _card_url(kind, object_id, archived=False))


@router.get("/{object_type}/{object_id}/archive/history")
async def get_archive_history(
    request: Request,
    object_type: str,
    object_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    archive_service: Annotated[ArchiveService, Depends(get_archive_service)],
):
    kind = _object_type(object_type)
    try:
        events = await archive_service.get_history(
            actor_id=current_user.id, object_type=kind, object_id=object_id
        )
    except (
        ObjectAccessDeniedError,
        ObjectNotFoundError,
        PermissionError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
    return templates.TemplateResponse(
        request=request,
        name="objects/archive_history.html",
        context={"events": events},
    )
