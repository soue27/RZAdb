from typing import Annotated

from fastapi import APIRouter, Depends

from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.auth.schemas import CurrentUserResponse

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)