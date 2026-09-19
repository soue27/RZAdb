from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.application.auth.service import AuthService, InvalidCredentialsError
from app.presentation.dependencies.services import get_auth_service

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.get("/login")
async def login_page() -> dict[str, str]:
    return {"message": "Login page"}


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