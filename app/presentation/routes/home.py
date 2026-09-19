from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user

router = APIRouter(
    tags=["home"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)

@router.get("/")
async def home(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    return templates.TemplateResponse(
        request=request,
        name="home/index.html",
        context={
            "current_user": current_user,
        },
    )