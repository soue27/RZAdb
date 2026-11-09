from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.otd.repository import OTDRepository
from app.application.otd.schemas import OTDDetails, OTDVersionDetails
from app.application.tasks.repository import TaskRepository
from app.domain.enums import (
    DocumentStatus,
    OTDPurpose,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.otd import OTD, OTDVersion

_AUTHOR_ROLES = {
    UserRole.ENGINEER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.SUPERADMIN,
}


class OTDService:
    """Управляет формуляром ОТД, его версиями и процессом согласования.
    """
    def __init__(
        self,
        repository: OTDRepository,
        access_service: AccessService,
        task_repository: TaskRepository | None = None,
    ) -> None:
        """Сохраняет зависимости для работы с ОТД, проверки доступа и задач.

        Args:
            repository: Репозиторий формуляров и версий ОТД.
            access_service: Централизованный сервис проверки доступа.
            task_repository: Необязательный репозиторий для проверки связанных задач.
        """
        self.repository = repository
        self.access_service = access_service
        self.task_repository = task_repository

    def _to_version_details(self, version: OTDVersion) -> OTDVersionDetails:
        """Преобразует доменную версию ОТД в DTO для отображения.

        Args:
            version: Версия формуляра.

        Returns:
            DTO с характеристиками версии и сведениями об авторе.
        """
        return OTDVersionDetails(
            id=version.id,
            version_number=version.version_number,
            status=version.status or DocumentStatus.DRAFT,
            effective_date=version.effective_date,
            panel_cabinet_type=version.panel_cabinet_type,
            panel_cabinet_serial=version.panel_cabinet_serial,
            panel_cabinet_manufacture_year=version.panel_cabinet_manufacture_year,
            terminal_type=version.terminal_type,
            terminal_serial=version.terminal_serial,
            terminal_manufacture_year=version.terminal_manufacture_year,
            urza_service_life=version.urza_service_life,
            software_version=version.software_version,
            ct_ratio=version.ct_ratio,
            vt_ratio=version.vt_ratio,
            urza_scheme_designation=version.urza_scheme_designation,
            urza_purpose=version.urza_purpose,
            created_at=version.created_at,
            created_by_full_name=(
                version.created_by_user.full_name
                if version.created_by_user is not None
                else None
            ),
        )

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> OTD | None:
        """Возвращает формуляр ОТД устройства, если пользователь имеет право чтения.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Формуляр ОТД или None при отсутствии доступа либо формуляра.
        """
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            return None

        return await self.repository.get_by_urza_id(urza_id)

    async def get_current_version(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> OTDVersion | None:
        """Возвращает текущую версию ОТД после проверки доступа к устройству.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Последняя активная версия или None.
        """
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            return None

        otd = await self.repository.get_by_urza_id(urza_id)

        if otd is None:
            return None

        return await self.repository.get_current_version(otd.id)

    async def get_versions(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> list[OTDVersion]:
        """Возвращает историю активных версий ОТД устройства.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Версии ОТД в порядке, заданном репозиторием; при отсутствии доступа
            или формуляра возвращает пустой список.
        """
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return []

        otd = await self.repository.get_by_urza_id(urza_id)
        if otd is None:
            return []

        return await self.repository.get_versions(otd.id)

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        effective_date: date,
        urza_service_life: int,
        urza_purpose: OTDPurpose,
        task_id: UUID | None = None,
        **version_fields,
    ) -> OTD:
        """Создаёт формуляр ОТД и его первую версию.

        Проверяет право изменения, роль автора и отсутствие существующего формуляра.
        Если передана задача, проверяет, что она подходит для создания результата ОТД.

        Args:
            user_id: Идентификатор автора.
            urza_id: Идентификатор устройства.
            effective_date: Дата вступления версии в силу.
            urza_service_life: Срок службы устройства.
            urza_purpose: Назначение устройства по ОТД.
            task_id: Необязательная задача, в рамках которой создаётся результат.
                **version_fields: Дополнительные технические характеристики версии.

        Returns:
            Созданный формуляр ОТД.

        Raises:
            PermissionError: Если пользователь не имеет права изменения.
            ValueError: Если формуляр уже существует или автор/задача не подходят.
        """
        if not await self.access_service.can_modify_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Изменение архивной URZA запрещено")

        await self._check_author(user_id)

        existing_otd = await self.repository.get_by_urza_id(urza_id)

        if existing_otd is not None:
            raise ValueError("OTD для данного URZA уже существует")

        if task_id is not None:
            await self.validate_task_for_result(user_id, urza_id, task_id)

        otd = OTD(
            urza_id=urza_id,
            created_by=user_id,
            updated_by=user_id,
        )

        await self.repository.add(otd)

        version = OTDVersion(
            otd_id=otd.id,
            version_number=1,
            effective_date=effective_date,
            urza_service_life=urza_service_life,
            urza_purpose=urza_purpose,
            task_id=task_id,
            created_by=user_id,
            updated_by=user_id,
            **version_fields,
        )

        await self.repository.add_version(version)

        return otd

    async def get_version_details(
            self,
            user_id: UUID,
            version_id: UUID,
    ) -> OTDVersionDetails | None:
        """Возвращает DTO версии ОТД после проверки принадлежности версии устройству.

        Args:
            user_id: Идентификатор пользователя.
            version_id: Идентификатор версии.

        Returns:
            DTO версии или None, если версия недоступна.
        """
        version = await self.repository.get_version_by_id(version_id)

        if version is None:
            return None

        otd = await self.repository.get_by_id(version.otd_id)

        if otd is None:
            return None

        if not await self.access_service.can_access_urza(
                user_id,
                otd.urza_id,
        ):
            return None

        return self._to_version_details(version)

    async def create_version(
            self,
            user_id: UUID,
            otd_id: UUID,
            effective_date: date,
            urza_service_life: int,
            urza_purpose: OTDPurpose,
            **kwargs,
    ) -> OTDVersion:
        """Создаёт следующую версию существующего формуляра ОТД.

        Args:
            user_id: Идентификатор автора.
            otd_id: Идентификатор формуляра.
            effective_date: Дата вступления версии в силу.
            urza_service_life: Срок службы устройства.
            urza_purpose: Назначение устройства по ОТД.
                **kwargs: Дополнительные характеристики новой версии.

        Returns:
            Созданная версия ОТД.

        Raises:
            PermissionError: Если пользователь не имеет права изменения.
            ValueError: Если формуляр или автор не подходят для операции.
        """
        otd = await self.repository.get_by_id(otd_id)

        if otd is None:
            raise ValueError("OTD не найден")

        if not await self.access_service.can_modify_urza(
                user_id,
                otd.urza_id,
        ):
            raise PermissionError("Изменение архивной URZA запрещено")

        await self._check_author(user_id)

        task_id = kwargs.pop("task_id", None)
        if task_id is not None:
            await self.validate_task_for_result(user_id, otd.urza_id, task_id)

        max_version = await self.repository.get_max_version_number(otd_id)
        version_number = (max_version or 0) + 1

        version = OTDVersion(
            otd_id=otd_id,
            version_number=version_number,
            effective_date=effective_date,
            urza_service_life=urza_service_life,
            urza_purpose=urza_purpose,
            task_id=task_id,
            created_by=user_id,
            updated_by=user_id,
            **kwargs,
        )

        await self.repository.add_version(version)

        return version

    async def validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ):
        """Проверяет, что задача допускает создание результата ОТД.

        Args:
            user_id: Идентификатор исполнителя.
            urza_id: Идентификатор устройства.
            task_id: Идентификатор задачи.

        Returns:
            Проверенная задача.

        Raises:
            PermissionError: Если пользователь не имеет доступа или не назначен исполнителем.
            ValueError: Если задача не относится к ОТД или не находится в работе.
        """
        if self.task_repository is None:
            raise RuntimeError("TaskRepository не настроен для результата ОТД.")
        task = await self.task_repository.get_by_id(task_id)
        if task is None or task.deleted_at is not None:
            raise ValueError("Активная задача не найдена.")
        if task.work_type is not TaskWorkType.OTD:
            raise ValueError("Задача не предназначена для работы с ОТД.")
        if task.urza_id != urza_id:
            raise ValueError("Задача относится к другому устройству РЗА.")
        if task.assigned_to != user_id:
            raise PermissionError(
                "Создать результат может только назначенный исполнитель задачи."
            )
        if task.status is not TaskStatus.IN_PROGRESS:
            raise ValueError("Создавать результат можно только по задаче в работе.")
        if await self.repository.get_version_by_task_id(task_id) is not None:
            raise ValueError("Для задачи уже существует активный результат ОТД.")
        return task

    async def _get_accessible_version(
        self,
        user_id: UUID,
        version_id: UUID,
        urza_id: UUID,
    ) -> OTDVersion:
        """Находит версию ОТД и проверяет её принадлежность указанному устройству.

        Args:
            user_id: Идентификатор пользователя.
            version_id: Идентификатор версии.
            urza_id: Идентификатор устройства.

        Returns:
            Доступная версия ОТД.

        Raises:
            ValueError: Если версия не найдена или относится к другому устройству.
        """
        version = await self.repository.get_version_by_id(version_id)
        if version is None:
            raise ValueError("Версия ОТД не найдена.")
        otd = await self.repository.get_by_id(version.otd_id)
        if otd is None or otd.urza_id != urza_id:
            raise ValueError("Версия ОТД не принадлежит указанной URZA.")
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")
        return version

    async def submit_for_review(
        self, user_id: UUID, urza_id: UUID, version_id: UUID
    ) -> OTDVersion:
        """Отправляет версию ОТД на согласование после проверки автора и доступа.

        Args:
            user_id: Идентификатор автора.
            urza_id: Идентификатор устройства.
            version_id: Идентификатор версии.

        Returns:
            Версия ОТД в статусе UNDER_REVIEW.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or user.role not in _AUTHOR_ROLES:
            raise PermissionError("Отправлять ОТД на согласование запрещено.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        return await self.repository.save_version(version)

    async def approve(
        self, user_id: UUID, urza_id: UUID, version_id: UUID
    ) -> OTDVersion:
        """Утверждает версию ОТД руководителем соответствующего предприятия.

        Args:
            user_id: Идентификатор руководителя.
            urza_id: Идентификатор устройства.
            version_id: Идентификатор версии.

        Returns:
            Утверждённая версия ОТД.

        Raises:
            PermissionError: Если пользователь не является допустимым проверяющим.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        version.status = DocumentStatus.APPROVED
        version.updated_by = user_id
        return await self.repository.save_version(version)

    async def return_to_draft(
        self, user_id: UUID, urza_id: UUID, version_id: UUID
    ) -> OTDVersion:
        """Возвращает версию ОТД с согласования на доработку.

        Args:
            user_id: Идентификатор руководителя.
            urza_id: Идентификатор устройства.
            version_id: Идентификатор версии.

        Returns:
            Версия ОТД в статусе DRAFT.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        version.status = DocumentStatus.DRAFT
        version.updated_by = user_id
        return await self.repository.save_version(version)

    async def _check_manager_reviewer(self, user_id: UUID, urza_id: UUID) -> None:
        """Проверяет, что пользователь — руководитель предприятия, которому принадлежит УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Raises:
            PermissionError: Если пользователь не имеет роли или области ответственности MANAGER.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать ОТД может только MANAGER.")
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Нет доступа к активной URZA в зоне ответственности.")

    async def _check_author(self, user_id: UUID) -> None:
        """Проверяет, что пользователь имеет роль, допускающую создание или изменение ОТД.

        Args:
            user_id: Идентификатор пользователя.

        Raises:
            PermissionError: Если роль пользователя не входит в список разрешённых.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if (
            user is None
            or not user.active
            or user.deleted_at is not None
            or user.role not in _AUTHOR_ROLES
        ):
            raise PermissionError("Создавать ОТД может только активный пользователь с соответствующей ролью.")

    async def get_available_actions(
        self, user_id: UUID, version: OTDVersion
    ) -> set[str]:
        """Возвращает действия, доступные пользователю для конкретной версии ОТД.

        Args:
            user_id: Идентификатор пользователя.
            version: Проверяемая версия.

        Returns:
            Множество кодов действий с учётом статуса, роли и области доступа.
        """
        if version.deleted_at is not None:
            return set()
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        otd = await self.repository.get_by_id(version.otd_id)
        if otd is None or not await self.access_service.can_modify_urza(
            user_id, otd.urza_id
        ):
            return set()
        if version.task_id is not None:
            return set()
        if version.status is DocumentStatus.DRAFT:
            return {"submit"} if user.role in _AUTHOR_ROLES else set()
        if version.status is DocumentStatus.UNDER_REVIEW:
            try:
                await self._check_manager_reviewer(user_id, otd.urza_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        if version.status is DocumentStatus.APPROVED:
            return {"new_version"} if user.role in _AUTHOR_ROLES else set()
        return set()

    async def get_available_create_actions(
        self, user_id: UUID, urza_id: UUID
    ) -> set[str]:
        """Возвращает действия, доступные пользователю при создании ОТД для устройства.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Множество кодов доступных действий.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if (
            user is None
            or not user.active
            or user.deleted_at is not None
            or user.role not in _AUTHOR_ROLES
            or not await self.access_service.can_modify_urza(user_id, urza_id)
        ):
            return set()
        otd = await self.repository.get_by_urza_id(urza_id)
        if otd is None:
            return {"create"}
        current = await self.repository.get_current_version(otd.id)
        if current is None or current.status is DocumentStatus.APPROVED:
            return {"new_version"}
        return set()

    async def get_details(
            self,
            user_id: UUID,
            urza_id: UUID,
            version_id: UUID | None = None,
    ) -> OTDDetails | None:
        """Возвращает формуляр ОТД с текущей, выбранной и историческими версиями.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.
            version_id: Необязательная версия, которую требуется выбрать в деталях.

        Returns:
            DTO формуляра или None, если формуляр недоступен.
        """
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            return None

        otd = await self.repository.get_by_urza_id(urza_id)

        if otd is None:
            return None

        versions = await self.repository.get_versions(otd.id)

        version_details = [
            self._to_version_details(version)
            for version in versions
        ]

        current_version = (
            version_details[0]
            if version_details
            else None
        )

        selected_version = current_version

        if version_id is not None:
            selected_version = next(
                (
                    version
                    for version in version_details
                    if version.id == version_id
                ),
                None,
            )

            if selected_version is None:
                return None

        return OTDDetails(
            id=otd.id,
            current_version=current_version,
            selected_version=selected_version,
            versions=version_details,
        )
