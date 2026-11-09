from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


class URZAInstructionRepository:
    """Выполняет запросы к инструкциям УРЗА, версиям и операциям публикации.
    """
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        instruction_id: UUID,
    ) -> URZAInstruction | None:
        """Находит активную инструкцию УРЗА по идентификатору.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Инструкция или None.
        """
        return await self.session.scalar(
            select(URZAInstruction).where(
                URZAInstruction.id == instruction_id,
                URZAInstruction.deleted_at.is_(None),
            )
        )

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> URZAInstruction | None:
        """Находит активную инструкцию указанного УРЗА.

        Args:
            urza_id: Идентификатор устройства.

        Returns:
            Инструкция или None.
        """
        query = select(URZAInstruction).where(
            URZAInstruction.urza_id == urza_id,
            URZAInstruction.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> URZAInstructionVersion | None:
        """Находит активную версию инструкции УРЗА.

        Args:
            version_id: Идентификатор версии.

        Returns:
            Версия или None.
        """
        query = select(URZAInstructionVersion).where(
            URZAInstructionVersion.id == version_id,
            URZAInstructionVersion.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def add_instruction(
        self,
        instruction: URZAInstruction,
    ) -> URZAInstruction:
        """Добавляет инструкцию УРЗА и выполняет flush без commit.

        Args:
            instruction: Создаваемая инструкция.

        Returns:
            Добавленная модель инструкции.
        """
        self.session.add(instruction)
        await self.session.flush()
        return instruction

    async def add_version(
        self,
        version: URZAInstructionVersion,
    ) -> URZAInstructionVersion:
        """Добавляет версию инструкции УРЗА и выполняет flush без commit.

        Args:
            version: Создаваемая версия.

        Returns:
            Добавленная версия.
        """
        self.session.add(version)
        await self.session.flush()
        return version

    async def save(
        self,
        version: URZAInstructionVersion,
    ) -> URZAInstructionVersion:
        """Синхронизирует изменения версии инструкции с базой данных без commit.

        Args:
            version: Изменённая версия.

        Returns:
            Та же модель версии.
        """
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_current_version(
            self,
            instruction_id: UUID,
    ) -> URZAInstructionVersion | None:
        """Возвращает текущую опубликованную версию инструкции УРЗА.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Последняя утверждённая версия или None.
        """
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id
                == instruction_id,
                URZAInstructionVersion.status == DocumentStatus.APPROVED,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(
                URZAInstructionVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_max_version_number(
        self,
        instruction_id: UUID,
    ) -> int | None:
        """Возвращает максимальный номер версии инструкции.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Максимальный номер версии или None.
        """
        query = select(func.max(URZAInstructionVersion.version_number)).where(
            URZAInstructionVersion.urza_instruction_id == instruction_id,
        )
        return await self.session.scalar(query)

    async def get_max_published_version_number(
        self,
        instruction_id: UUID,
    ) -> int | None:
        """Возвращает максимальный номер опубликованной версии инструкции.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Максимальный опубликованный номер или None.
        """
        query = select(func.max(URZAInstructionVersion.version_number)).where(
            URZAInstructionVersion.urza_instruction_id == instruction_id,
            URZAInstructionVersion.status == DocumentStatus.APPROVED,
        )
        return await self.session.scalar(query)

    async def lock_instruction_for_versioning(
        self,
        instruction_id: UUID,
    ) -> None:
        """Блокирует инструкцию на время создания или нумерации новой версии.

        Args:
            instruction_id: Идентификатор инструкции.
        """
        await self.session.scalar(
            select(URZAInstruction.id)
            .where(URZAInstruction.id == instruction_id)
            .with_for_update()
        )

    async def lock_and_refresh_version(
        self,
        version: URZAInstructionVersion,
    ) -> None:
        """Блокирует и перечитывает версию перед изменением её статуса или номера.

        Args:
            version: Загруженная версия инструкции.
        """
        await self.lock_instruction_for_versioning(
            version.urza_instruction_id,
        )
        await self.session.refresh(version)

    async def assign_next_published_number(
        self,
        version: URZAInstructionVersion,
    ) -> int:
        """Назначает версии следующий номер публикации с учётом текущих опубликованных версий.

        Args:
            version: Версия, которую требуется опубликовать.

        Returns:
            Назначенный номер публикации.
        """
        instruction_id = version.urza_instruction_id
        await self.lock_instruction_for_versioning(instruction_id)
        published_max = await self.get_max_published_version_number(
            instruction_id,
        )
        next_number = (published_max or 0) + 1

        conflict = await self.session.scalar(
            select(URZAInstructionVersion).where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.version_number == next_number,
                URZAInstructionVersion.id != version.id,
            )
        )
        if conflict is not None:
            max_number = await self.get_max_version_number(instruction_id)
            conflict.version_number = (max_number or 0) + 1
            await self.session.flush()

        return next_number

    async def get_latest_working_version(
        self,
        instruction_id: UUID,
    ) -> URZAInstructionVersion | None:
        """Возвращает последнюю рабочую версию инструкции, не обязательно опубликованную.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Последняя рабочая версия или None.
        """
        query = (
            select(URZAInstructionVersion)
            .options(selectinload(URZAInstructionVersion.creator))
            .where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(URZAInstructionVersion.version_number.desc())
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_working_versions(
        self,
        instruction_id: UUID,
    ) -> list[URZAInstructionVersion]:
        """Возвращает рабочие версии инструкции, доступные в процессе подготовки.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Список рабочих версий.
        """
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
                selectinload(URZAInstructionVersion.scan_file),
                selectinload(URZAInstructionVersion.editable_file),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.deleted_at.is_(None),
                URZAInstructionVersion.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .order_by(
                URZAInstructionVersion.created_at.desc(),
                URZAInstructionVersion.id.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_versions(
            self,
            instruction_id: UUID,
    ) -> list[URZAInstructionVersion]:
        """Возвращает историю версий инструкции УРЗА.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Список версий в порядке, заданном репозиторием.
        """
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
                selectinload(URZAInstructionVersion.scan_file),
                selectinload(URZAInstructionVersion.editable_file),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id
                == instruction_id,
                URZAInstructionVersion.status == DocumentStatus.APPROVED,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(
                URZAInstructionVersion.version_number.desc(),
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def list_standalone_work_items(self) -> list[URZAInstructionVersion]:
        """Возвращает версии инструкций УРЗА, не связанные с задачами, для рабочего списка.
        """
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.urza_instruction),
                selectinload(URZAInstructionVersion.creator),
            )
            .where(
                URZAInstructionVersion.deleted_at.is_(None),
                URZAInstructionVersion.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .order_by(
                URZAInstructionVersion.created_at.desc(),
                URZAInstructionVersion.id.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())
