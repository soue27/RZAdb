from typing import Annotated

from fastapi import APIRouter, Depends

from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user

router = APIRouter(
    tags=["home"],
)


@router.get("/")
async def home(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    return {
        "message": "RZAdb",
        "user": current_user.full_name,
    }