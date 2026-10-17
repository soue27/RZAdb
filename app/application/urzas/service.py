from uuid import UUID

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.urzas.repository import URZARepository
from app.application.urzas.schemas import (
    URZAConnectionInfo,
    URZACreate,
    URZADetails,
    URZASubstationInfo,
)
from app.domain.urza import URZA


class URZANameConflictError(ValueError):
    """Имя URZA уже используется в этом присоединении."""


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

    async def create(
            self,
            *,
            connection_id: UUID,
            actor_id: UUID,
            data: URZACreate,
    ) -> URZADetails:
        if await self.repository.exists_by_name(
                connection_id,
                data.dispatch_name,
        ):
            raise URZANameConflictError(
                "УРЗА с таким диспетчерским наименованием уже существует."
            )
        urza = URZA(
            connection_id=connection_id,
            dispatch_name=data.dispatch_name,
            rdu_subordination=data.rdu_subordination,
            inventory_number=data.inventory_number,
            commissioning_date=data.commissioning_date,
            status=data.status,
            element_base=data.element_base,
            category=data.category,
            room_category=data.room_category,
            complexity=data.complexity,
            created_by=actor_id,
            updated_by=actor_id,
        )

        await self.repository.add(urza)

        return await self.get_details(urza.id)