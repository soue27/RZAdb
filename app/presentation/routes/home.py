from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.application.tasks.statistics import TaskStatisticsService
from app.application.tree.service import TreeService
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_task_statistics_service,
    get_tree_service,
)

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
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    tree = await tree_service.get_tree(
        user_id=current_user.id,
    )

    return templates.TemplateResponse(
        request=request,
        name="home/index.html",
        context={
            "current_user": current_user,
            "tree": tree,
        },
    )

@router.get("/task-statistics")
async def task_statistics(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    statistics_service: Annotated[
        TaskStatisticsService,
        Depends(get_task_statistics_service),
    ],
):
    return templates.TemplateResponse(
        request=request,
        name="components/task_statistics_content.html",
        context={
            "statistics": await statistics_service.get_for_user(current_user.id),
        },
    )
