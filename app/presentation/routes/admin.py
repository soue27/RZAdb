
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.users.repository import UserRepository
from app.domain.user import User
from app.infrastructure.database.session import get_session
from app.presentation.auth.dependencies import require_superadmin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)


@router.get("/")
async def admin_dashboard(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    users = await UserRepository(session).get_all()

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={
            "current_user": current_user,
            "users": users,
        },
    )
