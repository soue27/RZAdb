from uuid import UUID

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.substations.repository import SubstationRepository
from app.application.substations.schemas import SubstationDetails, SubstationUpdate


class SubstationService:
    """Бизнес-логика работы с подстанциями."""

    def __init__(self, repository: SubstationRepository) -> None:
        self.repository = repository

    async def update_details(
        self, substation_id: UUID, data: SubstationUpdate
    ) -> SubstationDetails:
        substation = await self.repository.get_by_id(substation_id)
        if substation is None:
            raise ObjectNotFoundError
        for field, value in data.model_dump().items():
            setattr(substation, field, value)
        await self.repository.save(substation)
        return await self.get_details(substation_id)

    async def get_details(self, substation_id: UUID) -> SubstationDetails:
        substation = await self.repository.get_by_id(substation_id)

        if substation is None:
            raise ObjectNotFoundError

        return SubstationDetails(
            id=substation.id,
            dispatch_name=substation.dispatch_name,
            highest_voltage=substation.highest_voltage,
            sap_code=substation.sap_code,
            asureo_code=substation.asureo_code,
            address=substation.address,
            latitude=substation.latitude,
            longitude=substation.longitude,
            operational_current_type=substation.operational_current_type,
        )
