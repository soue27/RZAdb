"""Маршрут проверки доступности HTTP-приложения."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.engine import async_session_factory

router = APIRouter(
    tags=["health"],
)


@router.get("/health")
async def health() -> dict[str, str]:
    """Возвращает простой статус доступности HTTP-приложения.
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, str]:
    """Проверяет доступность приложения и PostgreSQL безопасным read-only запросом."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ready"}
