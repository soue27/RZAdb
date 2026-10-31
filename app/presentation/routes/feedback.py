import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.feedback.service import FeedbackService
from app.application.enterprises.repository import EnterpriseRepository
from app.core.config import get_settings
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_enterprise_repository,
    get_feedback_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

templates = Jinja2Templates(directory="app/presentation/templates")


def _get_csrf_token(request: Request) -> str:
    token = request.session.get("feedback_csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        request.session["feedback_csrf_token"] = token

    return token


def _validate_csrf_token(request: Request, token: str) -> None:
    session_token = request.session.get("feedback_csrf_token")

    if (
        not session_token
        or not secrets.compare_digest(session_token, token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недействительный CSRF-токен.",
        )


def _render_feedback(
    request: Request,
    current_user: User,
    *,
    error: str | None = None,
    success: bool = False,
    status_code: int = status.HTTP_200_OK,
    message: str = "",
):
    return templates.TemplateResponse(
        request=request,
        name="feedback/index.html",
        context={
            "current_user": current_user,
            "csrf_token": _get_csrf_token(request),
            "max_length": get_settings().feedback_max_length,
            "error": error,
            "success": success,
            "message": message,
        },
        status_code=status_code,
    )


@router.get("/feedback")
async def feedback_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    sent: bool = False,
):
    return _render_feedback(
        request,
        current_user,
        success=sent,
    )


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        FeedbackService,
        Depends(get_feedback_service),
    ],
    enterprise_repository: Annotated[
        EnterpriseRepository,
        Depends(get_enterprise_repository),
    ],
    message: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
):
    _validate_csrf_token(request, csrf_token)

    message = message.strip()
    max_length = get_settings().feedback_max_length

    if not message:
        return _render_feedback(
            request,
            current_user,
            error="Введите текст сообщения.",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if len(message) > max_length:
        return _render_feedback(
            request,
            current_user,
            error=f"Сообщение не должно превышать {max_length} символов.",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    enterprise_name = None

    if current_user.enterprise_id is not None:
        enterprise = await enterprise_repository.get_by_id(
            current_user.enterprise_id,
        )
        if enterprise is not None:
            enterprise_name = enterprise.full_name

    try:
        await service.send(
            user_id=str(current_user.id),
            full_name=current_user.full_name,
            email=current_user.email,
            role=current_user.role.value,
            enterprise_name=enterprise_name,
            message=message,
        )
    except Exception:
        logger.exception(
            "Failed to send feedback email for user %s",
            current_user.id,
        )
        return _render_feedback(
            request,
            current_user,
            error=(
                "Не удалось отправить сообщение. "
                "Попробуйте позднее или обратитесь к администратору другим способом."
            ),
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return RedirectResponse(
        url="/feedback?sent=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )