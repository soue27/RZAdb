import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.notifications.service import NotificationService
from app.domain.enums import TaskWorkType
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_notification_service

router = APIRouter(tags=["notifications"])

templates = Jinja2Templates(directory="app/presentation/templates")

PAGE_SIZE = 20

EVENT_LABELS = {
    "assigned": "Вам назначено задание",
    "rejected": "Исполнитель отказался от задания",
    "reassigned": "Изменён исполнитель задания",
    "updated": "Изменены условия задания",
    "review_rejected": "Задание возвращено на доработку",
}

WORK_TYPE_LABELS = {
    TaskWorkType.OTD: "ОТД",
    TaskWorkType.SETTINGS: "Уставки",
    TaskWorkType.SCHEMES: "Схемы",
    TaskWorkType.MAINTENANCE: "Техническое обслуживание",
    TaskWorkType.PROGRAM: "Программы",
    TaskWorkType.INSTRUCTION: "Инструкция",
}


def _get_csrf_token(request: Request) -> str:
    token = request.session.get("notifications_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["notifications_csrf_token"] = token
    return token


def _validate_csrf_token(request: Request, token: str) -> None:
    session_token = request.session.get("notifications_csrf_token")

    if (
        not session_token
        or not secrets.compare_digest(session_token, token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недействительный CSRF-токен.",
        )


def _notification_context(notification):
    history = notification.task_history
    task = history.task

    object_name = (
        task.urza.dispatch_name
        if task.urza is not None
        else task.substation.dispatch_name
    )

    event_label = EVENT_LABELS.get(
        history.event_type,
        "Изменение задания",
    )

    if history.event_type == "reassigned":
        if notification.recipient_id == history.previous_assignee_id:
            event_label = "Задание снято с вас"
        elif notification.recipient_id == history.new_assignee_id:
            event_label = "Вам назначено задание"

    return {
        "notification": notification,
        "event_label": event_label,
        "task": task,
        "object_name": object_name,
        "work_type_label": WORK_TYPE_LABELS.get(
            task.work_type,
            task.work_type.value,
        ),
        "history": history,
        "actor_name": (
            history.actor.full_name
            if history.actor is not None
            else None
        ),
    }


@router.get("/notifications")
async def notifications_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        NotificationService,
        Depends(get_notification_service),
    ],
    offset: int = 0,
):
    notifications = await service.get_unread(
        recipient_id=current_user.id,
        limit=PAGE_SIZE,
        offset=max(offset, 0),
    )
    total = await service.count_unread(recipient_id=current_user.id)

    items = [
        _notification_context(notification)
        for notification in notifications
    ]

    return templates.TemplateResponse(
        request=request,
        name="notifications/index.html",
        context={
            "current_user": current_user,
            "notifications": items,
            "total": total,
            "offset": max(offset, 0),
            "page_size": PAGE_SIZE,
            "csrf_token": _get_csrf_token(request),
        },
    )


@router.get("/notifications/count")
async def notifications_count(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        NotificationService,
        Depends(get_notification_service),
    ],
):
    count = await service.count_unread(recipient_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="notifications/_count.html",
        context={"notification_count": count},
    )


@router.post("/notifications/{notification_id}/open")
async def open_notification(
    notification_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        NotificationService,
        Depends(get_notification_service),
    ],
    csrf_token: Annotated[str, Form()],
):
    _validate_csrf_token(request, csrf_token)

    notification = await service.get_by_id(
        notification_id=notification_id,
        recipient_id=current_user.id,
    )

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Уведомление не найдено.",
        )

    task_id = notification.task_history.task_id

    await service.mark_as_read(
        notification_id=notification_id,
        recipient_id=current_user.id,
    )

    return RedirectResponse(
        url=f"/tasks/{task_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )