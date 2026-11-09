from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


class RZAInstructionRepository:
    """Выполняет запросы к инструкциям РЗА подстанций и их версиям.
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
    ) -> RZAInstruction | None:
        """Находит инструкцию РЗА по идентификатору.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Инструкция или None.
        """
        return await self.session.get(
            RZAInstruction,
            instruction_id,
        )

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> RZAInstruction | None:
        """Находит инструкцию РЗА подстанции.

        Args:
            substation_id: Идентификатор подстанции.

        Returns:
            Инструкция или None.
        """
        query = select(RZAInstruction).where(
            RZAInstruction.substation_id == substation_id,
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> RZAInstructionVersion | None:
        """Находит версию инструкции РЗА по идентификатору.

        Args:
            version_id: Идентификатор версии.

        Returns:
            Версия инструкции или None.
        """
        return await self.session.get(
            RZAInstructionVersion,
            version_id,
        )

    async def add_instruction(
        self,
        instruction: RZAInstruction,
    ) -> RZAInstruction:
        """Добавляет инструкцию РЗА и выполняет flush без commit.

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
        version: RZAInstructionVersion,
    ) -> RZAInstructionVersion:
        """Добавляет версию инструкции РЗА и выполняет flush без commit.

        Args:
            version: Создаваемая версия.

        Returns:
            Добавленная версия инструкции.
        """
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_current_version(
            self,
            instruction_id: UUID,
    ) -> RZAInstructionVersion | None:
        """Возвращает последнюю версию инструкции РЗА с данными связанных файлов.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Версия с наибольшим номером или None.
        """
        query = (
            select(RZAInstructionVersion)
            .options(
                selectinload(RZAInstructionVersion.scan_file),
                selectinload(RZAInstructionVersion.editable_file),
            )
            .where(
                RZAInstructionVersion.rza_instruction_id == instruction_id,
            )
            .order_by(
                RZAInstructionVersion.version_number.desc(),
            )
            .limit(1)
        )

        return await self.session.scalar(query)

    async def get_versions(
            self,
            instruction_id: UUID,
    ) -> list[RZAInstructionVersion]:
        """Возвращает версии инструкции с авторами и связанными файлами.

        Args:
            instruction_id: Идентификатор инструкции.

        Returns:
            Список версий в порядке нумерации.
        """
        query = (
            select(RZAInstructionVersion)
            .options(
                selectinload(RZAInstructionVersion.creator),
                selectinload(RZAInstructionVersion.scan_file),
                selectinload(RZAInstructionVersion.editable_file),
            )
            .where(
                RZAInstructionVersion.rza_instruction_id == instruction_id,
            )
            .order_by(
                RZAInstructionVersion.version_number.desc(),
            )
        )

        result = await self.session.scalars(query)
        return list(result.all())

    async def save(self, version: RZAInstructionVersion) -> RZAInstructionVersion:
        """Синхронизирует изменения версии инструкции с базой данных без commit.

        Args:
            version: Изменённая версия.

        Returns:
            Та же модель версии.
        """
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def list_standalone_work_items(self) -> list[RZAInstructionVersion]:
        """Возвращает самостоятельные версии инструкций РЗА для рабочего списка.

        Returns:
            Версии, не связанные с задачами, в рабочих статусах.
        """
        latest = (
            select(
                RZAInstructionVersion.rza_instruction_id.label("instruction_id"),
                func.max(RZAInstructionVersion.version_number).label("version_number"),
            )
            .where(RZAInstructionVersion.deleted_at.is_(None))
            .group_by(RZAInstructionVersion.rza_instruction_id)
            .subquery()
        )
        query = (
            select(RZAInstructionVersion)
            .options(
                selectinload(RZAInstructionVersion.rza_instruction)
                .selectinload(RZAInstruction.substation),
                selectinload(RZAInstructionVersion.creator),
            )
            .where(
                RZAInstructionVersion.deleted_at.is_(None),
                RZAInstructionVersion.task_id.is_(None),
                RZAInstructionVersion.rza_instruction_id == latest.c.instruction_id,
                RZAInstructionVersion.version_number == latest.c.version_number,
            )
            .order_by(RZAInstructionVersion.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())
