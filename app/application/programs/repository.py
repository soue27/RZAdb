from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.program import Program


class ProgramRepository:
    """Выполняет запросы к программам и связанным с ними файлам.
    """
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
            self,
            program_id: UUID,
    ) -> Program | None:
        """Находит программу по идентификатору и загружает связанные файлы.

        Args:
            program_id: Идентификатор программы.

        Returns:
            Программа или None.
        """
        query = (
            select(Program)
            .options(
                selectinload(Program.scan_file),
                selectinload(Program.editable_file),
            )
            .where(
                Program.id == program_id,
            )
        )

        return await self.session.scalar(query)

    async def get_by_urza_id(
            self,
            urza_id: UUID,
    ) -> list[Program]:
        """Возвращает программы указанного УРЗА с данными авторов.

        Args:
            urza_id: Идентификатор устройства.

        Returns:
            Программы в порядке номера программы.
        """
        query = (
            select(Program)
            .options(
                selectinload(Program.creator),
            )
            .where(
                Program.urza_id == urza_id,
            )
            .order_by(
                Program.program_number,
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def get_by_task_id(
        self,
        task_id: UUID,
    ) -> Program | None:
        """Находит программу, связанную с задачей.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            Программа или None.
        """
        query = select(Program).where(
            Program.task_id == task_id,
        )

        return await self.session.scalar(query)

    async def add(
        self,
        program: Program,
    ) -> Program:
        """Добавляет программу и выполняет flush без commit.

        Args:
            program: Создаваемая программа.

        Returns:
            Добавленная модель программы.
        """
        self.session.add(program)
        await self.session.flush()

        return program

    async def save(
        self,
        program: Program,
    ) -> Program:
        """Синхронизирует изменения программы с базой данных без commit.

        Args:
            program: Изменённая программа.

        Returns:
            Та же модель программы.
        """
        await self.session.flush()

        return program

    async def list_standalone_under_review(self) -> list[Program]:
        """Возвращает самостоятельные программы на согласовании.

        Returns:
            Активные программы без связанной задачи с загруженными УРЗА и автором.
        """
        query = (
            select(Program)
            .options(
                selectinload(Program.urza),
                selectinload(Program.creator),
            )
            .where(
                Program.task_id.is_(None),
                Program.status == DocumentStatus.UNDER_REVIEW,
                Program.deleted_at.is_(None),
            )
            .order_by(Program.updated_at.desc())
        )

        result = await self.session.scalars(query)
        return list(result.all())

    async def list_standalone_work_items(self) -> list[Program]:
        """Возвращает самостоятельные программы для рабочего списка.

        Включает активные записи в статусах DRAFT, UNDER_REVIEW и APPROVED.

        Returns:
            Программы с загруженными УРЗА и автором.
        """
        query = (
            select(Program)
            .options(
                selectinload(Program.urza),
                selectinload(Program.creator),
            )
            .where(
                Program.task_id.is_(None),
                Program.status.in_((
                                    DocumentStatus.DRAFT,
                                    DocumentStatus.UNDER_REVIEW,
                                    DocumentStatus.APPROVED,
                                )
                ),
                Program.deleted_at.is_(None),
            )
            .order_by(Program.created_at.desc(), Program.id.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())
