from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.urza_instructions.repository import URZAInstructionRepository
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.enums import DocumentStatus, UserRole
from app.domain.urza_instruction import URZAInstruction, URZAInstructionVersion

_AUTHOR_ROLES = {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}


class URZAInstructionService:
    """Управляет инструкцией УРЗА, её рабочими и опубликованными версиями, а также согласованием.
    """
    def __init__(
        self,
        repository: URZAInstructionRepository,
        access_service: AccessService,
        user_repository: UserRepository,
        urza_repository: URZARepository,
    ) -> None:
        """Сохраняет репозитории и сервис проверки доступа.

        Args:
            repository: Репозиторий инструкций и версий.
            access_service: Централизованный сервис проверки доступа.
            user_repository: Репозиторий пользователей.
            urza_repository: Репозиторий устройств РЗА.
        """
        self.repository = repository
        self.access_service = access_service
        self.user_repository = user_repository
        self.urza_repository = urza_repository

    async def _status_for_creator(self, user_id: UUID) -> DocumentStatus:
        """Определяет начальный статус версии инструкции по роли автора.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            UNDER_REVIEW для руководителя или DRAFT для разрешённых авторов.

        Raises:
            ValueError: Если пользователь не найден.
            PermissionError: Если роль не допускает создание инструкции.
        """
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if user.role is UserRole.MANAGER:
            return DocumentStatus.UNDER_REVIEW
        if user.role in _AUTHOR_ROLES:
            return DocumentStatus.DRAFT
        raise PermissionError("Создавать инструкции с текущей ролью запрещено.")

    async def _check_manager_reviewer(self, user_id: UUID, urza_id: UUID) -> None:
        """Проверяет, что согласование выполняет руководитель предприятия указанного УРЗА.

        Args:
            user_id: Идентификатор проверяющего.
            urza_id: Идентификатор устройства.

        Raises:
            ValueError: Если пользователь или устройство не найдены либо не определена подстанция.
            PermissionError: Если пользователь неактивен, не MANAGER или не отвечает за предприятие.
        """
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать инструкцию может только Manager.")
        urza = await self.urza_repository.get_by_id(urza_id)
        if urza is None:
            raise ValueError("URZA не найден.")
        if urza.connection is None or urza.connection.substation is None:
            raise ValueError("Не удалось определить Production Department URZA.")
        if user.enterprise_id != urza.connection.substation.enterprise_id:
            raise PermissionError("Manager не отвечает за данный Production Department.")

    async def _get_accessible_instruction(self, user_id: UUID, instruction_id: UUID) -> URZAInstruction:
        """Находит инструкцию УРЗА и проверяет право пользователя на доступ к ней.
        """
        instruction = await self.repository.get_by_id(instruction_id)
        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена.")
        if not await self.access_service.can_access_urza(user_id, instruction.urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return instruction

    async def get_by_urza(self, user_id: UUID, urza_id: UUID) -> URZAInstruction | None:
        """Возвращает инструкцию указанного УРЗА после проверки доступа.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Инструкция или None.
        """
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return await self.repository.get_by_urza_id(urza_id)

    async def create(
        self, user_id: UUID, urza_id: UUID, effective_date: date,
        scan_file_id: UUID, editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstruction:
        """Создаёт инструкцию УРЗА и её первую версию.

        Args:
            user_id: Идентификатор автора.
            urza_id: Идентификатор устройства.
            effective_date: Дата вступления версии в силу.
            scan_file_id: Идентификатор обязательного скана.
            editable_file_id: Необязательный редактируемый файл.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.

        Returns:
            Созданная инструкция.
        """
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")
        status = await self._status_for_creator(user_id)
        if await self.repository.get_by_urza_id(urza_id) is not None:
            raise ValueError("Инструкция РЗА для данного URZA уже существует")
        instruction = URZAInstruction(urza_id=urza_id, created_by=user_id, updated_by=user_id)
        await self.repository.add_instruction(instruction)
        await self.repository.add_version(URZAInstructionVersion(
            urza_instruction_id=instruction.id, version_number=1, status=status,
            effective_date=effective_date, change_description=change_description,
            change_justification=change_justification, created_by=user_id,
            updated_by=user_id, scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        ))
        return instruction

    async def get_current_version(self, user_id: UUID, urza_id: UUID) -> URZAInstructionVersion | None:
        """Возвращает текущую опубликованную версию инструкции УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Текущая версия или None.
        """
        instruction = await self.get_by_urza(user_id, urza_id)
        if instruction is None:
            return None
        return await self.repository.get_current_version(instruction.id)

    async def get_versions(self, user_id: UUID, urza_id: UUID) -> list[URZAInstructionVersion]:
        """Возвращает историю версий инструкции УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Список версий.
        """
        instruction = await self.get_by_urza(user_id, urza_id)
        if instruction is None:
            return []
        return await self.repository.get_versions(instruction.id)

    async def get_working_versions(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[URZAInstructionVersion]:
        """Возвращает рабочие версии инструкции, доступные пользователю.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Список рабочих версий.
        """
        instruction = await self.get_by_urza(user_id, urza_id)
        if instruction is None:
            return []
        return await self.repository.get_working_versions(instruction.id)

    async def get_version_by_id(self, user_id: UUID, version_id: UUID) -> URZAInstructionVersion | None:
        """Возвращает версию инструкции по идентификатору после проверки доступа.

        Args:
            user_id: Идентификатор пользователя.
            version_id: Идентификатор версии.

        Returns:
            Версия или None.
        """
        version = await self.repository.get_version_by_id(version_id)
        if version is None:
            return None
        instruction = await self.repository.get_by_id(version.urza_instruction_id)
        if instruction is None:
            return None
        if not await self.access_service.can_modify_urza(user_id, instruction.urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")
        return version

    async def create_version(
        self, user_id: UUID, instruction_id: UUID, effective_date: date,
        scan_file_id: UUID, editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstructionVersion:
        """Создаёт новую рабочую версию инструкции УРЗА.

        Args:
            user_id: Идентификатор автора.
            instruction_id: Идентификатор инструкции.
            effective_date: Дата вступления версии в силу.
            scan_file_id: Идентификатор обязательного скана.
            editable_file_id: Необязательный редактируемый файл.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.

        Returns:
            Созданная версия инструкции.
        """
        instruction = await self._get_accessible_instruction(user_id, instruction_id)
        status = await self._status_for_creator(user_id)
        await self.repository.lock_instruction_for_versioning(instruction.id)
        max_version = await self.repository.get_max_version_number(instruction_id)
        version = URZAInstructionVersion(
            urza_instruction_id=instruction.id,
            version_number=(max_version or 0) + 1,
            status=status,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )
        return await self.repository.add_version(version)

    async def submit_for_review(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        """Отправляет рабочую версию инструкции на согласование.

        Args:
            user_id: Идентификатор автора.
            version_id: Идентификатор версии.
            urza_id: Идентификатор устройства.

        Returns:
            Версия в статусе UNDER_REVIEW.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if user.role not in _AUTHOR_ROLES:
            raise PermissionError("Отправлять инструкцию на согласование может только ENGINEER, ADMIN или SUPERADMIN.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def approve(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        """Утверждает версию инструкции руководителем.

        Args:
            user_id: Идентификатор руководителя.
            version_id: Идентификатор версии.
            urza_id: Идентификатор устройства.

        Returns:
            Опубликованная версия инструкции.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        await self.repository.lock_and_refresh_version(version)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только версию на согласовании.")
        version.version_number = await self.repository.assign_next_published_number(
            version,
        )
        version.status = DocumentStatus.APPROVED
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def return_to_draft(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        """Возвращает версию инструкции с согласования на доработку.

        Args:
            user_id: Идентификатор руководителя.
            version_id: Идентификатор версии.
            urza_id: Идентификатор устройства.

        Returns:
            Версия в статусе DRAFT.
        """
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть в черновик можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        version.status = DocumentStatus.DRAFT
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def _get_accessible_version(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        """Находит версию инструкции и проверяет её принадлежность указанному УРЗА.
        """
        version = await self.repository.get_version_by_id(version_id)
        if version is None:
            raise ValueError("Версия инструкции не найдена.")
        instruction = await self.repository.get_by_id(version.urza_instruction_id)
        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена.")
        if instruction.urza_id != urza_id:
            raise ValueError("Инструкция не принадлежит указанной URZA.")
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")
        return version

    async def get_available_actions(self, user_id: UUID, version: URZAInstructionVersion) -> set[str]:
        """Возвращает действия, доступные пользователю для версии инструкции.

        Args:
            user_id: Идентификатор пользователя.
            version: Проверяемая версия.

        Returns:
            Множество кодов действий с учётом статуса, роли и доступа.
        """
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        if version.status is DocumentStatus.DRAFT:
            return {"submit"} if user.role in _AUTHOR_ROLES else set()
        if version.status is DocumentStatus.UNDER_REVIEW and user.role is UserRole.MANAGER:
            try:
                instruction = await self.repository.get_by_id(version.urza_instruction_id)
                if instruction is None:
                    return set()
                await self._check_manager_reviewer(user_id, instruction.urza_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        if version.status is DocumentStatus.APPROVED:
            return {"new_version"} if user.role in _AUTHOR_ROLES | {UserRole.MANAGER} else set()
        return set()
