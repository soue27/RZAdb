from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.auth.service import AuthService, InvalidCredentialsError
from app.presentation.dependencies.services import get_auth_service

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
        url="/",
        status_code=status.HTTP_303_SEE_OTHER,
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