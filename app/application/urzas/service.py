from uuid import UUID

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.urzas.repository import URZARepository
from app.application.urzas.schemas import (
    URZAConnectionInfo,
    URZADetails,
    URZASubstationInfo,
)


class URZAService:
    """Бизнес-логика работы с устройствами РЗА."""

    def __init__(self, repository: URZARepository) -> None:
        self.repository = repository

    async def get_details(self, urza_id: UUID) -> URZADetails:
        urza = await self.repository.get_by_id(urza_id)

        if urza is None:
            raise ObjectNotFoundError

        return URZADetails(
            id=urza.id,
            dispatch_name=urza.dispatch_name,
            rdu_subordination=urza.rdu_subordination,
            inventory_number=urza.inventory_number,
            commissioning_date=urza.commissioning_date,
            status=urza.status,
            element_base=urza.element_base,
            category=urza.category,
            room_category=urza.room_category,
            complexity=urza.complexity,
            connection=URZAConnectionInfo(
                id=urza.connection.id,
                dispatch_name=urza.connection.dispatch_name,
            ),
            substation=URZASubstationInfo(
                id=urza.connection.substation.id,
                dispatch_name=urza.connection.substation.dispatch_name,
            ),
        )