from uuid import UUID

from app.application.enterprises.repository import EnterpriseRepository
from app.application.enterprises.schemas import (
    EnterpriseDetails,
    EnterpriseUpdate,
)
from app.application.objects.exceptions import ObjectNotFoundError
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


class EnterpriseService:
    """Бизнес-логика производственных отделений."""

    def __init__(self, repository: EnterpriseRepository) -> None:
        """Сохраняет репозиторий предприятий.

        Args:
            repository: Репозиторий для чтения и сохранения предприятий.
        """
        self.repository = repository

    async def get_department(self, enterprise_id: UUID) -> EnterpriseDetails:
        """Возвращает сведения о производственном отделении.

        Args:
            enterprise_id: Идентификатор предприятия.

        Returns:
            DTO с данными производственного отделения.

        Raises:
            ObjectNotFoundError: Если предприятие отсутствует, архивировано
                или не относится к типу DEPARTMENT.
        """
        enterprise = await self._get_department_model(enterprise_id)
        return EnterpriseDetails.model_validate(enterprise)

    async def update_department(
        self,
        enterprise_id: UUID,
        data: EnterpriseUpdate,
        *,
        actor_id: UUID,
    ) -> EnterpriseDetails:
        """Обновляет сведения производственного отделения.

        Изменяет только поля, переданные в DTO, фиксирует инициатора изменения
        и сохраняет модель через репозиторий.

        Args:
            enterprise_id: Идентификатор отделения.
            data: Проверенные новые значения полей.
            actor_id: Идентификатор пользователя, выполнившего изменение.

        Returns:
            Обновлённые сведения об отделении.

        Raises:
            ObjectNotFoundError: Если отделение отсутствует, архивировано
                или имеет другой тип.
        """
        enterprise = await self._get_department_model(enterprise_id)

        for field, value in data.model_dump().items():
            setattr(enterprise, field, value)

        enterprise.updated_by = actor_id
        await self.repository.save(enterprise)

        return await self.get_department(enterprise_id)

    async def _get_department_model(self, enterprise_id: UUID) -> Enterprise:
        enterprise = await self.repository.get_by_id(enterprise_id)

        if (
            enterprise is None
            or enterprise.deleted_at is not None
            or enterprise.type != EnterpriseType.DEPARTMENT
        ):
            raise ObjectNotFoundError

        return enterprise