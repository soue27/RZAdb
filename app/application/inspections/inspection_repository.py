from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.inspection import Inspection


class InspectionRepository:
    """Работа с результатами осмотров через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        inspection_id: UUID,
    ) -> Inspection | None:
        """Находит результат осмотра по идентификатору.

        Args:
            inspection_id: Идентификатор результата.

        Returns:
            Результат осмотра или None.
        """
        return await self.session.get(Inspection, inspection_id)

    async def get_by_substation_id(
            self,
            substation_id: UUID,
    ) -> list[Inspection]:
        """Возвращает результаты осмотров указанной подстанции."""
        result = await self.session.scalars(
            select(Inspection)
            .options(
                selectinload(Inspection.scan_file),
                selectinload(Inspection.editable_file),
            )
            .where(
                Inspection.substation_id == substation_id,
                Inspection.deleted_at.is_(None),
            )
            .order_by(Inspection.inspection_date.desc())
        )

        return list(result)