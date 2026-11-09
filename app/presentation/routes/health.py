"""Маршрут проверки доступности HTTP-приложения."""

from fastapi import APIRouter

router = APIRouter(
    tags=["health"],
)


@router.get("/health")
async def health() -> dict[str, str]:
    """Возвращает простой статус доступности HTTP-приложения.
    """
    return {"status": "ok"}