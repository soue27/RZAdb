from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.enterprises.repository import EnterpriseRepository
from app.application.users.repository import UserRepository
from app.application.users.service import UserOperationError, UserService
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
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
        },
    )


@router.get("/users/new")
async def new_user_page(
    request: Request,
    current_user: Annotated[User, Depends(require_superadmin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    try:
        await service.archive(actor=current_user, user_id=user_id)
    except UserOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/", status_code=status.HTTP_303_SEE_OTHER)

