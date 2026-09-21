from uuid import UUID

from app.application.inspections.inspection_repository import InspectionRepository
from app.domain.inspection import Inspection


class InspectionService:
    """Бизнес-логика работы с результатами осмотров."""

    def __init__(
        self,
        repository: InspectionRepository,
    ) -> None:
        self.repository = repository

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[Inspection]:
        return await self.repository.get_by_substation_id(
            substation_id,
        )