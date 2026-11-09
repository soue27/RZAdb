from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


class SettingsRepository:
    """Выполняет запросы к формулярам уставок и отдельным записям изменений.
    """
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_form_by_id(self, form_id: UUID) -> SettingsForm | None:
        """Находит активный формуляр уставок по идентификатору.

        Args:
            form_id: Идентификатор формуляра.

        Returns:
            Формуляр уставок или None.
        """
        statement = select(SettingsForm).where(
            SettingsForm.id == form_id,
            SettingsForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_form_by_urza_id(self, urza_id: UUID) -> SettingsForm | None:
        """Находит активный формуляр уставок устройства.

        Args:
            urza_id: Идентификатор УРЗА.

        Returns:
            Формуляр уставок или None.
        """
        statement = select(SettingsForm).where(
            SettingsForm.urza_id == urza_id,
            SettingsForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_record_by_id(self, record_id: UUID) -> SettingsRecord | None:
        """Находит активную запись изменения уставок.

        Args:
            record_id: Идентификатор записи.

        Returns:
            Запись уставок или None.
        """
        statement = select(SettingsRecord).where(
            SettingsRecord.id == record_id,
            SettingsRecord.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_records(self, form_id: UUID) -> list[SettingsRecord]:
        """Возвращает активные записи указанного формуляра с данными авторов.

        Args:
            form_id: Идентификатор формуляра.

        Returns:
            Записи, отсортированные по дате изменения и времени создания.
        """
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
            )
            .options(selectinload(SettingsRecord.creator))
            .order_by(
                SettingsRecord.change_date.desc(),
                SettingsRecord.created_at.desc(),
                SettingsRecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_records_by_form_id(
        self,
        form_id: UUID,
    ) -> list[SettingsRecord]:
        """Возвращает записи формуляра; делегирует выборку методу get_records.

        Args:
            form_id: Идентификатор формуляра.

        Returns:
            Активные записи уставок.
        """
        return await self.get_records(form_id)

    async def get_current_approved(
        self,
        form_id: UUID,
    ) -> SettingsRecord | None:
        """Возвращает последнюю утверждённую запись уставок с данными автора и подписанной формы.

        Args:
            form_id: Идентификатор формуляра.

        Returns:
            Последняя утверждённая запись или None.
        """
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
                SettingsRecord.status == DocumentStatus.APPROVED,
            )
            .options(
                selectinload(SettingsRecord.creator),
                selectinload(SettingsRecord.signed_form_file),
            )
            .order_by(
                SettingsRecord.change_date.desc(),
                SettingsRecord.created_at.desc(),
                SettingsRecord.id.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_unfinished(self, form_id: UUID) -> SettingsRecord | None:
        """Находит незавершённую запись формуляра в статусе черновика или согласования.

        Args:
            form_id: Идентификатор формуляра.

        Returns:
            Незавершённая запись или None.
        """
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
                SettingsRecord.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def list_standalone_work_items(self) -> list[SettingsRecord]:
        """Возвращает самостоятельные записи уставок, не связанные с задачами.

        Включает активные записи в статусах DRAFT, UNDER_REVIEW и APPROVED.

        Returns:
            Записи с загруженными формуляром, УРЗА и автором.
        """
        statement = (
            select(SettingsRecord)
            .options(
                selectinload(SettingsRecord.settings_form).selectinload(
                    SettingsForm.urza
                ),
                selectinload(SettingsRecord.creator),
            )
            .where(
                SettingsRecord.task_id.is_(None),
                SettingsRecord.deleted_at.is_(None),
                SettingsRecord.status.in_(
                    (
                        DocumentStatus.DRAFT,
                        DocumentStatus.UNDER_REVIEW,
                        DocumentStatus.APPROVED,
                    )
                ),
            )
            .order_by(SettingsRecord.created_at.desc(), SettingsRecord.id.desc())
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def add_form(self, settings_form: SettingsForm) -> SettingsForm:
        """Добавляет формуляр уставок и выполняет flush без commit.

        Args:
            settings_form: Создаваемый формуляр.

        Returns:
            Добавленная модель формуляра.
        """
        self.session.add(settings_form)
        await self.session.flush()
        return settings_form

    async def add_record(self, settings_record: SettingsRecord) -> SettingsRecord:
        """Добавляет запись изменения уставок и выполняет flush без commit.

        Args:
            settings_record: Создаваемая запись.

        Returns:
            Добавленная модель записи.
        """
        self.session.add(settings_record)
        await self.session.flush()
        return settings_record

    async def save(self, settings_record: SettingsRecord) -> SettingsRecord:
        """Синхронизирует изменения записи уставок с базой данных без commit.

        Args:
            settings_record: Изменённая запись.

        Returns:
            Та же модель записи.
        """
        await self.session.flush()
        return settings_record

    async def flush(self) -> None:
        """Выполняет flush текущей сессии без фиксации транзакции.
        """
        await self.session.flush()
