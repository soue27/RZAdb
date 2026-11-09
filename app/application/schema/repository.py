from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.schema import SchemaForm, SchemaRecord


class SchemaRepository:
    """Выполняет запросы к формулярам схем и записям изменений схем.
"""
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
        session: Сессия текущей транзакции.
    """
        self.session = session

    async def get_form_by_id(
        self,
        schema_form_id: UUID,
    ) -> SchemaForm | None:
        """Находит активный формуляр схем по идентификатору.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Формуляр схем или None.
    """
        statement = select(SchemaForm).where(
            SchemaForm.id == schema_form_id,
            SchemaForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_form_by_urza_id(
        self,
        urza_id: UUID,
    ) -> SchemaForm | None:
        """Находит активный формуляр схем устройства.

        Args:
        urza_id: Идентификатор УРЗА.

        Returns:
        Формуляр схем или None.
    """
        statement = select(SchemaForm).where(
            SchemaForm.urza_id == urza_id,
            SchemaForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> SchemaRecord | None:
        """Находит активную запись схем и загружает сведения о её авторе.

        Args:
        record_id: Идентификатор записи.

        Returns:
        Запись схем или None.
    """
        statement = (
            select(SchemaRecord)
            .options(selectinload(SchemaRecord.creator))
            .where(
                SchemaRecord.id == record_id,
                SchemaRecord.deleted_at.is_(None),
            )
        )
        return await self.session.scalar(statement)

    async def get_record_by_id(
        self,
        record_id: UUID,
    ) -> SchemaRecord | None:
        """Возвращает запись по идентификатору через get_by_id.

        Args:
        record_id: Идентификатор записи.

        Returns:
        Активная запись схем или None.
    """
        return await self.get_by_id(record_id)

    async def list_active(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        """Возвращает активные записи формуляра с авторами и связанными файлами.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Записи в порядке убывания даты загрузки.
    """
        statement = (
            select(SchemaRecord)
            .options(
                selectinload(SchemaRecord.creator),
                selectinload(SchemaRecord.scan_file),
                selectinload(SchemaRecord.editable_file),
                selectinload(SchemaRecord.signed_form_file),
            )
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
            )
            .order_by(
                SchemaRecord.upload_date.desc(),
                SchemaRecord.created_at.desc(),
                SchemaRecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_form(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        """Возвращает активные записи формуляра через list_active.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Список записей схем.
    """
        return await self.list_active(schema_form_id)

    async def get_records_by_form_id(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        """Возвращает активные записи формуляра через list_active.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Список записей схем.
    """
        return await self.list_active(schema_form_id)

    async def get_current_approved(
        self,
        schema_form_id: UUID,
    ) -> SchemaRecord | None:
        """Возвращает последнюю утверждённую запись схем с данными автора и подписанной формы.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Последняя утверждённая запись или None.
    """
        statement = (
            select(SchemaRecord)
            .options(
                selectinload(SchemaRecord.creator),
                selectinload(SchemaRecord.signed_form_file),
            )
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
                SchemaRecord.status == DocumentStatus.APPROVED,
            )
            .order_by(
                SchemaRecord.upload_date.desc(),
                SchemaRecord.created_at.desc(),
                SchemaRecord.id.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_unfinished(
        self,
        schema_form_id: UUID,
    ) -> SchemaRecord | None:
        """Находит незавершённую запись формуляра в статусе черновика или согласования.

        Args:
        schema_form_id: Идентификатор формуляра.

        Returns:
        Незавершённая запись или None.
    """
        statement = (
            select(SchemaRecord)
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
                SchemaRecord.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def list_standalone_work_items(self) -> list[SchemaRecord]:
        """Возвращает самостоятельные записи схем, не связанные с задачами.

        Включает активные записи в статусах DRAFT, UNDER_REVIEW и APPROVED.

        Returns:
        Записи с загруженными формуляром, УРЗА и автором.
    """
        statement = (
            select(SchemaRecord)
            .options(
                selectinload(SchemaRecord.schema_form).selectinload(
                    SchemaForm.urza
                ),
                selectinload(SchemaRecord.creator),
            )
            .where(
                SchemaRecord.task_id.is_(None),
                SchemaRecord.deleted_at.is_(None),
                SchemaRecord.status.in_(
                    (
                        DocumentStatus.DRAFT,
                        DocumentStatus.UNDER_REVIEW,
                        DocumentStatus.APPROVED,
                    )
                ),
            )
            .order_by(SchemaRecord.created_at.desc(), SchemaRecord.id.desc())
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def add_form(
        self,
        schema_form: SchemaForm,
    ) -> SchemaForm:
        """Добавляет формуляр схем и выполняет flush без commit.

        Args:
        schema_form: Создаваемый формуляр.

        Returns:
        Добавленная модель формуляра.
    """
        self.session.add(schema_form)
        await self.session.flush()
        return schema_form

    async def add_record(
        self,
        record: SchemaRecord,
    ) -> SchemaRecord:
        """Добавляет запись схем и выполняет flush без commit.

        Args:
        record: Создаваемая запись.

        Returns:
        Добавленная модель записи.
    """
        self.session.add(record)
        await self.session.flush()
        return record

    async def save(
        self,
        record: SchemaRecord,
    ) -> SchemaRecord:
        """Синхронизирует изменения записи схем с базой данных без commit.

        Args:
        record: Изменённая запись.

        Returns:
        Та же модель записи.
    """
        await self.session.flush()
        return record

    async def rollback(self) -> None:
        """Откатывает текущую транзакцию SQLAlchemy-сессии.
    """
        await self.session.rollback()

    async def soft_delete(
        self,
        record: SchemaRecord,
        user_id: UUID,
    ) -> SchemaRecord:
        """Архивирует запись схем, сохраняя дату и пользователя, выполнившего операцию.

        Args:
        record: Запись для архивирования.
        user_id: Идентификатор пользователя.

        Returns:
        Архивированная запись.
    """
        now = datetime.now(UTC)
        record.deleted_at = now
        record.deleted_by = user_id
        record.updated_at = now
        record.updated_by = user_id
        await self.session.flush()
        return record
