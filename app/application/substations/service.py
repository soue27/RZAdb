from uuid import UUID

from app.application.substations.schemas import SubstationDetails
from app.application.substations.repository import SubstationRepository
from app.application.objects.exceptions import ObjectNotFoundError


class SubstationService:
    """Бизнес-логика работы с подстанциями."""

    def __init__(self, repository: SubstationRepository) -> None:
        self.repository = repository

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
        )