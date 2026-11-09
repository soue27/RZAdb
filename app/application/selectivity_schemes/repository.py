from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)


class SelectivitySchemeRepository:
    """Работа со схемами селективности через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        scheme_id: UUID,
    ) -> SelectivityScheme | None:
        """Находит схему селективности по идентификатору.

        Args:
            scheme_id: Идентификатор схемы.

        Returns:
            Схема селективности или None.
        """
        return await self.session.get(
            SelectivityScheme,
            scheme_id,
        )

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> SelectivityScheme | None:
        """Находит схему селективности подстанции.

        Args:
            substation_id: Идентификатор подстанции.

        Returns:
            Схема селективности или None.
        """
        query = (
            select(SelectivityScheme)
            .where(
                SelectivityScheme.substation_id == substation_id,
            )
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> SelectivitySchemeVersion | None:
        """Находит версию схемы селективности по идентификатору.

        Args:
            version_id: Идентификатор версии.

        Returns:
            Версия или None.
        """
        return await self.session.get(
            SelectivitySchemeVersion,
            version_id,
        )

    async def get_current_version(
        self,
        scheme_id: UUID,
    ) -> SelectivitySchemeVersion | None:
        """Возвращает последнюю версию схемы селективности с данными автора и файлов.

        Args:
            scheme_id: Идентификатор схемы.

        Returns:
            Версия с наибольшим номером или None.
        """
        query = (
            select(SelectivitySchemeVersion)
            .options(
                selectinload(SelectivitySchemeVersion.scan_file),
                selectinload(SelectivitySchemeVersion.editable_file),
                selectinload(SelectivitySchemeVersion.creator),
            )
            .where(
                SelectivitySchemeVersion.selectivity_scheme_id == scheme_id,
            )
            .order_by(
                SelectivitySchemeVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_versions(
        self,
        scheme_id: UUID,
    ) -> list[SelectivitySchemeVersion]:
        """Возвращает версии схемы селективности с данными авторов и файлов.

        Args:
            scheme_id: Идентификатор схемы.

        Returns:
            Список версий в порядке убывания номера.
        """
        query = (
            select(SelectivitySchemeVersion)
            .options(
                selectinload(SelectivitySchemeVersion.scan_file),
                selectinload(SelectivitySchemeVersion.editable_file),
                selectinload(SelectivitySchemeVersion.creator),
            )
            .where(
                SelectivitySchemeVersion.selectivity_scheme_id == scheme_id,
            )
            .order_by(
                SelectivitySchemeVersion.version_number.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result)

    async def add_scheme(
        self,
        scheme: SelectivityScheme,
    ) -> SelectivityScheme:
        """Добавляет схему селективности и выполняет flush без commit.

        Args:
            scheme: Создаваемая схема.

        Returns:
            Добавленная модель схемы.
        """
        self.session.add(scheme)
        await self.session.flush()
        return scheme

    async def add_version(
        self,
        version: SelectivitySchemeVersion,
    ) -> SelectivitySchemeVersion:
        """Добавляет версию схемы селективности и выполняет flush без commit.

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
        version: SelectivitySchemeVersion,
    ) -> SelectivitySchemeVersion:
        """Синхронизирует изменения версии схемы с базой данных без commit.

        Args:
            version: Изменённая версия.

        Returns:
            Та же модель версии.
        """
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def list_standalone_work_items(self) -> list[SelectivitySchemeVersion]:
        """Возвращает самостоятельные версии схем селективности для рабочего списка.

        Returns:
            Версии, не связанные с задачами.
        """
        latest = (
            select(
                SelectivitySchemeVersion.selectivity_scheme_id.label("scheme_id"),
                func.max(SelectivitySchemeVersion.version_number).label("version_number"),
            )
            .where(SelectivitySchemeVersion.deleted_at.is_(None))
            .group_by(SelectivitySchemeVersion.selectivity_scheme_id)
            .subquery()
        )
        query = (
            select(SelectivitySchemeVersion)
            .options(
                selectinload(SelectivitySchemeVersion.selectivity_scheme)
                .selectinload(SelectivityScheme.substation),
                selectinload(SelectivitySchemeVersion.creator),
            )
            .where(
                SelectivitySchemeVersion.deleted_at.is_(None),
                SelectivitySchemeVersion.task_id.is_(None),
                SelectivitySchemeVersion.selectivity_scheme_id == latest.c.scheme_id,
                SelectivitySchemeVersion.version_number == latest.c.version_number,
            )
            .order_by(SelectivitySchemeVersion.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())
