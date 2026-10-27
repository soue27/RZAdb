from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.auth.service import AuthService, InvalidCredentialsError
from app.application.users.service import UserOperationError, UserService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_auth_service, get_user_service

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
    )

@router.post("/login")
async def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    try:
        user = await auth_service.authenticate(
            email=email,
            password=password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль.",
        ) from exc

    request.session["user_id"] = str(user.id)

    return RedirectResponse(
        url="/auth/change-password" if user.must_change_password else "/",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/change-password")
async def change_password_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    return templates.TemplateResponse(
        request=request,
        name="auth/change_password.html",
        context={"current_user": current_user, "error": None},
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    current_password: Annotated[str | None, Form()] = None,
):
    error = None
    if new_password != confirm_password:
        error = "Новый пароль и подтверждение не совпадают."
    else:
        try:
            await service.change_password(
                user=current_user,
                current_password=current_password,
                new_password=new_password,
            )
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        except UserOperationError as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="auth/change_password.html",
        context={"current_user": current_user, "error": error},
        status_code=400,
    )

@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()

    response = RedirectResponse(
        url="/auth/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(
        key="session",
        httponly=True,
        samesite="lax",
    )

    return response
