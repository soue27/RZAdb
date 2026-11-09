from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.rza_instructions.repository import (
    RZAInstructionRepository,
)
from app.application.rza_instructions.schemas import (
    RZAInstructionDetails,
    RZAInstructionVersionDetails,
)
from app.domain.enums import DocumentStatus, UserRole
from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


class RZAInstructionService:
    """Управляет инструкцией РЗА подстанции, её версиями и согласованием.
    """
    def __init__(
        self,
        repository: RZAInstructionRepository,
        access_service: AccessService,
    ) -> None:
        """Сохраняет репозиторий инструкции и сервис проверки доступа.

        Args:
            repository: Репозиторий инструкции РЗА.
            access_service: Централизованный сервис проверки доступа.
        """
        self.repository = repository
        self.access_service = access_service

    async def _status_for_creator(self, user_id: UUID) -> DocumentStatus:
        """Определяет начальный статус версии по роли автора.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            APPROVED для руководителя или DRAFT для разрешённых авторов.

        Raises:
            ValueError: Если пользователь отсутствует или неактивен.
            PermissionError: Если роль не допускает создание инструкции.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise ValueError("Пользователь не найден или неактивен.")
        if user.role is UserRole.MANAGER:
            return DocumentStatus.APPROVED
        if user.role in {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}:
            return DocumentStatus.DRAFT
        raise PermissionError("Создавать инструкцию с текущей ролью запрещено.")

    def _to_version_details(
            self,
            version: RZAInstructionVersion,
    ) -> RZAInstructionVersionDetails:
        """Преобразует версию инструкции в DTO для отображения.

        Args:
            version: Версия инструкции.

        Returns:
            DTO с атрибутами версии, автором и файлами.
        """
        return RZAInstructionVersionDetails(
            id=version.id,
            version_number=version.version_number,
            effective_date=version.effective_date,
            change_description=version.change_description,
            change_justification=version.change_justification,
            created_at=version.created_at,
            created_by_full_name=(
                version.creator.full_name
                if version.creator is not None
                else None
            ),
            scan_file_id=version.scan_file_id,
            scan_file_name=(
                version.scan_file.display_name
                if version.scan_file is not None
                else None
            ),
            editable_file_id=version.editable_file_id,
            editable_file_name=(
                version.editable_file.display_name
                if version.editable_file is not None
                else None
            ),
            status=version.status if isinstance(version.status, DocumentStatus) else DocumentStatus.DRAFT,
        )

    async def get_by_substation(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> RZAInstruction | None:
        """Возвращает инструкцию РЗА подстанции после проверки права чтения.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            Инструкция или None.
        """
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        return await self.repository.get_by_substation_id(
            substation_id,
        )

    async def create(
        self,
        user_id: UUID,
        substation_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
        task_id: UUID | None = None,
    ) -> RZAInstruction:
        """Создаёт инструкцию РЗА подстанции и её первую версию.

        Args:
            user_id: Идентификатор автора.
            substation_id: Идентификатор подстанции.
            effective_date: Дата вступления версии в силу.
            scan_file_id: Идентификатор обязательного скана.
            editable_file_id: Необязательный редактируемый файл.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.
            task_id: Необязательная связанная задача.

        Returns:
            Созданная инструкция.

        Raises:
            PermissionError: Если нет права изменения подстанции.
            ValueError: Если инструкция уже существует или роль автора недопустима.
        """
        if not await self.access_service.can_modify_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Изменение архивной подстанции запрещено")

        existing = await self.repository.get_by_substation_id(
            substation_id,
        )

        if existing is not None:
            raise ValueError(
                "Инструкция РЗА для данной подстанции уже существует"
            )

        instruction = RZAInstruction(
            substation_id=substation_id,
            created_by=user_id,
            updated_by=user_id,
        )
        initial_status = await self._status_for_creator(user_id)

        await self.repository.add_instruction(instruction)

        version = RZAInstructionVersion(
            rza_instruction_id=instruction.id,
            version_number=1,
            status=initial_status,
            task_id=task_id,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return instruction

    async def get_current_version(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> RZAInstructionVersion | None:
        """Возвращает текущую версию инструкции подстанции.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            Текущая версия или None.
        """
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        instruction = await self.repository.get_by_substation_id(
            substation_id,
        )

        if instruction is None:
            return None

        return await self.repository.get_current_version(
            instruction.id,
        )

    async def get_versions(
            self,
            user_id: UUID,
            substation_id: UUID,
    ) -> list[RZAInstructionVersionDetails]:
        """Возвращает историю версий инструкции подстанции.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            Список DTO версий.
        """
        if not await self.access_service.can_access_substation(
                user_id,
                substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        instruction = await self.repository.get_by_substation_id(
            substation_id,
        )

        if instruction is None:
            return []

        versions = await self.repository.get_versions(
            instruction.id,
        )

        return [
            self._to_version_details(version)
            for version in versions
        ]

    async def create_version(
        self,
        user_id: UUID,
        instruction_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
        task_id: UUID | None = None,
    ) -> RZAInstructionVersion:
        """Создаёт следующую версию существующей инструкции РЗА.

        Args:
            user_id: Идентификатор автора.
            instruction_id: Идентификатор инструкции.
            effective_date: Дата вступления версии в силу.
            scan_file_id: Идентификатор обязательного скана.
            editable_file_id: Необязательный редактируемый файл.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.
            task_id: Необязательная связанная задача.

        Returns:
            Созданная версия инструкции.
        """
        instruction = await self.repository.get_by_id(
            instruction_id,
        )

        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена")

        if not await self.access_service.can_modify_substation(
            user_id,
            instruction.substation_id,
        ):
            raise PermissionError("Изменение архивной подстанции запрещено")

        current_version = await self.repository.get_current_version(
            instruction_id,
        )

        if current_version is not None and current_version.status is DocumentStatus.UNDER_REVIEW:
            raise ValueError("Новая версия недоступна, пока текущая находится на согласовании.")
        initial_status = await self._status_for_creator(user_id)

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = RZAInstructionVersion(
            rza_instruction_id=instruction_id,
            version_number=version_number,
            status=initial_status,
            task_id=task_id,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return version

    async def get_details(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> RZAInstructionDetails | None:
        """Возвращает сводные данные инструкции и текущей версии подстанции.

        Args:
            user_id: Идентификатор пользователя.
            substation_id: Идентификатор подстанции.

        Returns:
            DTO инструкции или None.
        """
        instruction = await self.get_by_substation(
            user_id=user_id,
            substation_id=substation_id,
        )

        if instruction is None:
            return None

        version = await self.repository.get_current_version(
            instruction.id,
        )

        if version is None:
            return None

        return RZAInstructionDetails(
            instruction_id=instruction.id,
            version_id=version.id,
            version_number=version.version_number,
            effective_date=version.effective_date,
            change_description=version.change_description,
            change_justification=version.change_justification,
            scan_file_id=version.scan_file_id,
            scan_file_name=(
                version.scan_file.display_name
                if version.scan_file is not None
                else None
            ),
            editable_file_id=version.editable_file_id,
            editable_file_name=(
                version.editable_file.display_name
                if version.editable_file is not None
                else None
            ),
        )

    async def _get_accessible_version(
        self, user_id: UUID, version_id: UUID, substation_id: UUID
    ) -> RZAInstructionVersion:
        """Находит версию и проверяет её принадлежность доступной инструкции подстанции.
        """
        version = await self.repository.get_version_by_id(version_id)
        if version is None or version.deleted_at is not None:
            raise ValueError("Версия инструкции не найдена.")
        instruction = await self.repository.get_by_id(version.rza_instruction_id)
        if instruction is None or instruction.substation_id != substation_id:
            raise ValueError("Инструкция не принадлежит указанной подстанции.")
        if not await self.access_service.can_modify_substation(user_id, substation_id):
            raise PermissionError("Изменение архивной подстанции запрещено.")
        return version

    async def _check_reviewer(self, user_id: UUID, substation_id: UUID) -> None:
        """Проверяет право руководителя согласовывать инструкцию указанной подстанции.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        substation = await self.access_service.substation_repository.get_by_id(substation_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать инструкцию может только MANAGER.")
        if substation is None:
            raise ValueError("Подстанция не найдена.")
        if user.enterprise_id != substation.enterprise_id:
            raise PermissionError("MANAGER не отвечает за данную подстанцию.")
        if not await self.access_service.can_access_substation(user_id, substation_id):
            raise PermissionError("Доступ к подстанции запрещён.")

    async def submit_for_review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID
    ) -> RZAInstructionVersion:
        """Отправляет версию инструкции на согласование.

        Args:
            user_id: Идентификатор автора.
            substation_id: Идентификатор подстанции.
            version_id: Идентификатор версии.

        Returns:
            Версия в статусе UNDER_REVIEW.
        """
        version = await self._get_accessible_version(user_id, version_id, substation_id)
        user = await self.access_service.user_repository.get_by_id(user_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        if user is None or user.role not in {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}:
            raise PermissionError("Отправить инструкцию может только автор документа.")
        if version.created_by != user_id:
            raise PermissionError("Отправить инструкцию может только её автор.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        return await self.repository.save(version)

    async def review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID, *, approve: bool
    ) -> RZAInstructionVersion:
        """Принимает решение по версии инструкции: утверждает её или возвращает на доработку.

        Args:
            user_id: Идентификатор руководителя.
            substation_id: Идентификатор подстанции.
            version_id: Идентификатор версии.
            approve: True для утверждения, False для возврата в черновик.

        Returns:
            Обновлённая версия инструкции.
        """
        version = await self._get_accessible_version(user_id, version_id, substation_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Решение доступно только для версии на согласовании.")
        await self._check_reviewer(user_id, substation_id)
        version.status = DocumentStatus.APPROVED if approve else DocumentStatus.DRAFT
        version.updated_by = user_id
        return await self.repository.save(version)

    async def get_available_actions(
        self, user_id: UUID, version: RZAInstructionVersion
    ) -> set[str]:
        """Возвращает действия, доступные пользователю для версии инструкции.

        Args:
            user_id: Идентификатор пользователя.
            version: Проверяемая версия.

        Returns:
            Множество кодов действий с учётом статуса, роли и доступа.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        version_record = await self.repository.get_version_by_id(version.id)
        if version_record is None or version_record.deleted_at is not None:
            return set()
        instruction = await self.repository.get_by_id(
            version_record.rza_instruction_id
        )
        if (
            instruction is None
            or instruction.deleted_at is not None
            or not await self.access_service.can_modify_substation(
                user_id, instruction.substation_id
            )
        ):
            return set()
        if version_record.status is DocumentStatus.DRAFT:
            return {"submit", "new_version"} if version_record.created_by == user_id and user.role in {
                UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN
            } else set()
        if version_record.status is DocumentStatus.UNDER_REVIEW:
            try:
                await self._check_reviewer(user_id, instruction.substation_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        return {"new_version"} if user.role in {
            UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.MANAGER
        } else set()
