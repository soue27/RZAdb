from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.users.repository import UserRepository
from app.domain.user import User
from app.domain.enums import UserRole
from app.infrastructure.database.session import get_session
from app.presentation.auth.dependencies import require_superadmin
from app.application.enterprises.repository import EnterpriseRepository

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
    role_filter: str | None = None,
    status_filter: str | None = None,
    enterprise_filter: str | None = None,
):

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

    role_labels = {
        "superadmin": "Суперпользователь",
        "admin": "Администратор",
        "specialist": "Специалист",
        "manager": "Руководитель",
        "engineer": "Инженер",
    }

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
        },
    )

