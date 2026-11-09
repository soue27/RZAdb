from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.otd import OTD, OTDVersion


class OTDRepository:
    """Выполняет запросы к формулярам ОТД и их версиям.
    """
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        otd_id: UUID,
    ) -> OTD | None:
        """Находит активный формуляр ОТД по идентификатору.

        Args:
            otd_id: Идентификатор формуляра.

        Returns:
            Формуляр или None.
        """
        query = select(OTD).where(
            OTD.id == otd_id,
            OTD.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> OTD | None:
        """Находит активный формуляр ОТД устройства.

        Args:
            urza_id: Идентификатор УРЗА.

        Returns:
            Формуляр ОТД или None.
        """
        query = select(OTD).where(
            OTD.urza_id == urza_id,
            OTD.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
            self,
            version_id: UUID,
    ) -> OTDVersion | None:
        """Находит активную версию ОТД и загружает сведения о её авторе.

        Args:
            version_id: Идентификатор версии.

        Returns:
            Версия ОТД или None.
        """
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.id == version_id,
                OTDVersion.deleted_at.is_(None),
            )
        )

        return await self.session.scalar(query)

    async def add(
            self,
            otd: OTD,
    ) -> OTD:
        """Добавляет формуляр ОТД и выполняет flush без commit.

        Args:
            otd: Создаваемый формуляр.

        Returns:
            Добавленная модель формуляра.
        """
        self.session.add(otd)
        await self.session.flush()
        return otd

    async def add_version(
            self,
            version: OTDVersion,
    ) -> OTDVersion:
        """Добавляет новую версию ОТД и выполняет flush без commit.

        Args:
            version: Создаваемая версия формуляра.

        Returns:
            Добавленная версия.
        """
        self.session.add(version)
        await self.session.flush()
        return version

    async def save_version(self, version: OTDVersion) -> OTDVersion:
        """Синхронизирует изменения версии ОТД и обновляет серверные поля.

        Args:
            version: Изменённая версия.

        Returns:
            Та же модель версии.
        """
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def get_current_version(
            self,
            otd_id: UUID,
    ) -> OTDVersion | None:
        """Возвращает последнюю активную версию формуляра ОТД.

        Args:
            otd_id: Идентификатор формуляра.

        Returns:
            Версия с наибольшим номером или None.
        """
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.otd_id == otd_id,
                OTDVersion.deleted_at.is_(None),
            )
            .order_by(OTDVersion.version_number.desc())
        )

        return await self.session.scalar(query)

    async def get_versions(self, otd_id: UUID) -> list[OTDVersion]:
        """Возвращает все активные версии формуляра ОТД в обратном порядке нумерации.

        Args:
            otd_id: Идентификатор формуляра.

        Returns:
            Список версий с загруженными сведениями об авторах.
        """
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.otd_id == otd_id,
                OTDVersion.deleted_at.is_(None),
            )
            .order_by(OTDVersion.version_number.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_max_version_number(self, otd_id: UUID) -> int | None:
        """Возвращает максимальный номер версии формуляра.

        Args:
            otd_id: Идентификатор формуляра.

        Returns:
            Максимальный номер или None, если версий нет.
        """
        query = select(func.max(OTDVersion.version_number)).where(
            OTDVersion.otd_id == otd_id
        )
        return await self.session.scalar(query)

    async def get_version_by_task_id(self, task_id: UUID) -> OTDVersion | None:
        """Находит активную версию ОТД, созданную в рамках задачи.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            Версия ОТД или None.
        """
        query = select(OTDVersion).where(
            OTDVersion.task_id == task_id,
            OTDVersion.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def list_standalone_work_items(self) -> list[OTDVersion]:
        """Возвращает версии ОТД без связанной задачи для самостоятельного рабочего списка.

        Returns:
            Активные версии с загруженными формуляром, УРЗА и автором.
        """
        query = (
            select(OTDVersion)
            .options(
                selectinload(OTDVersion.created_by_user),
                selectinload(OTDVersion.otd).selectinload(OTD.urza),
            )
            .join(OTD, OTDVersion.otd_id == OTD.id)
            .where(
                OTDVersion.task_id.is_(None),
                OTDVersion.deleted_at.is_(None),
                OTD.deleted_at.is_(None),
            )
            .order_by(OTDVersion.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

