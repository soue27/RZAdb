from uuid import UUID

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.substations.repository import SubstationRepository
from app.application.substations.schemas import (
    SubstationCreate,
    SubstationDetails,
    SubstationUpdate,
)
from app.domain.substation import Substation


class SubstationService:
    """Бизнес-логика работы с подстанциями."""

    def __init__(self, repository: SubstationRepository) -> None:
        """Сохраняет репозиторий подстанций.

        Args:
        repository: Репозиторий для чтения и сохранения подстанций.

        """
        self.repository = repository


    async def update_details(
        self,
        substation_id: UUID,
        actor_id: UUID,
        data: SubstationUpdate,
    ) -> SubstationDetails:
        """Обновляет основные сведения существующей активной подстанции.

        Args:
        substation_id: Идентификатор подстанции.
        actor_id: Идентификатор пользователя, выполнившего изменение.
        data: Проверенные новые значения полей.

        Returns:
        Обновлённые сведения о подстанции.

        Raises:
        ObjectNotFoundError: Если подстанция отсутствует или архивирована.

        """
        substation = await self.repository.get_by_id(substation_id)
        if substation is None or substation.deleted_at is not None:
            raise ObjectNotFoundError

        for field, value in data.model_dump().items():
            setattr(substation, field, value)

        substation.updated_by = actor_id

        await self.repository.save(substation)
        return await self.get_details(substation_id)


    async def get_details(
        self, substation_id: UUID, *, include_archived: bool = False
    ) -> SubstationDetails:
        """Возвращает сведения о подстанции.

        Args:
        substation_id: Идентификатор подстанции.
        include_archived: Разрешает получить сведения об архивной записи.

        Returns:
        DTO с основными сведениями и техническими характеристиками.

        Raises:
        ObjectNotFoundError: Если подстанция не найдена или архивирована,
            а include_archived не установлен.

        """
        substation = await self.repository.get_by_id(substation_id)

        if substation is None or (substation.deleted_at is not None and not include_archived):
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

    async def create(
            self,
            enterprise_id: UUID,
            actor_id: UUID,
            data: SubstationCreate,
    ) -> SubstationDetails:
        """Создаёт подстанцию в указанном предприятии.

        Args:
        enterprise_id: Идентификатор предприятия-владельца.
        actor_id: Идентификатор пользователя, создающего запись.
        data: Проверенные поля новой подстанции.

        Returns:
        DTO созданной подстанции.

        """
        substation = Substation(
            enterprise_id=enterprise_id,
            created_by=actor_id,
            updated_by=actor_id,
            **data.model_dump(),
        )
        await self.repository.save(substation)
        return await self.get_details(substation.id)
