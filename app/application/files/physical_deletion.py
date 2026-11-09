import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.files.owner_repository import FileOwnerRepository
from app.domain.enums import UserRole
from app.domain.file import File
from app.domain.inspection import Inspection
from app.domain.maintenance import TORecord
from app.domain.otd import OTD, OTDVersion
from app.domain.program import Program
from app.domain.rza_instruction import RZAInstruction, RZAInstructionVersion
from app.domain.rza_settings import SettingsForm
from app.domain.schema import SchemaForm, SchemaRecord
from app.domain.selectivity_scheme import SelectivityScheme, SelectivitySchemeVersion
from app.domain.settings_record import SettingsRecord
from app.domain.urza_instruction import URZAInstruction, URZAInstructionVersion
from app.infrastructure.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeletionTarget:
    """Описание модели и полей, необходимых для удаления конкретного типа документной записи.
    """
    model: type
    parent_field: str | None
    parent_model: type | None
    parent_owner_field: str | None
    scope: str


@dataclass(frozen=True)
class DeletionResult:
    """Результат удаления доменной записи и признак ошибки очистки бинарного файла.
    """
    owner_id: UUID
    file_cleanup_failed: bool


TARGETS = {
    "inspection": DeletionTarget(Inspection, None, None, None, "substation_id"),
    "rza_instruction_version": DeletionTarget(
        RZAInstructionVersion, "rza_instruction_id", RZAInstruction, "substation_id", "version"
    ),
    "selectivity_scheme_version": DeletionTarget(
        SelectivitySchemeVersion, "selectivity_scheme_id", SelectivityScheme, "substation_id", "version"
    ),
    "otd_version": DeletionTarget(OTDVersion, "otd_id", OTD, "urza_id", "version"),
    "settings": DeletionTarget(SettingsRecord, "settings_form_id", SettingsForm, "urza_id", "urza"),
    "schema": DeletionTarget(SchemaRecord, "schema_form_id", SchemaForm, "urza_id", "urza"),
    "maintenance": DeletionTarget(TORecord, None, None, None, "urza_id"),
    "program": DeletionTarget(Program, None, None, None, "urza_id"),
    "urza_instruction_version": DeletionTarget(
        URZAInstructionVersion, "urza_instruction_id", URZAInstruction, "urza_id", "version"
    ),
}


class PhysicalDeletionService:
    """Физически удаляет документные записи и больше не используемые ими файлы с проверкой прав доступа.
    """
    def __init__(
        self,
        *,
        session: AsyncSession,
        access_service: AccessService,
        file_owners: FileOwnerRepository,
        storage: ObjectStorage,
    ) -> None:
        """Сохраняет зависимости для транзакционного удаления записей и очистки хранилища.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            access_service: Сервис проверки доступа к владельцам.
            file_owners: Репозиторий для проверки оставшихся ссылок на файлы.
            storage: Адаптер объектного хранилища.
        """
        self.session = session
        self.access_service = access_service
        self.file_owners = file_owners
        self.storage = storage

    async def delete(
        self, *, kind: str, record_id: UUID, user_id: UUID,
        expected_owner_id: UUID | None = None,
    ) -> DeletionResult:
        """Удаляет документную запись и очищает связанные файлы, если они больше не используются.

        Проверяет роль и доступ пользователя, блокирует удаляемую запись и её родителя,
        проверяет ожидаемого владельца. Сначала фиксирует удаление в БД, затем удаляет
        освободившиеся бинарные объекты из хранилища.

        Args:
            kind: Ключ типа удаляемой записи из TARGETS.
            record_id: Идентификатор записи.
            user_id: Идентификатор пользователя, выполняющего удаление.
            expected_owner_id: Необязательный ожидаемый идентификатор владельца.

        Returns:
            Идентификатор владельца и признак неудачной очистки файлов.

        Raises:
            PermissionError: Если роль или область доступа не позволяют удаление.
            LookupError: Если запись, документ или ожидаемый владелец не найдены.
            IntegrityError: Если удаление блокируется ограничением целостности.
            RuntimeError: Если другая ошибка не позволяет завершить удаление.
        """
        target = TARGETS[kind]
        model = target.model
        user = await self.access_service.user_repository.get_by_id(user_id)
        if (
            user is None
            or not user.active
            or user.deleted_at is not None
            or user.role not in {UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN}
        ):
            raise PermissionError("Недостаточно прав для удаления записи.")

        record = await self.session.scalar(
            select(model).where(model.id == record_id, model.deleted_at.is_(None)).with_for_update()
        )
        if record is None:
            raise LookupError("Запись не найдена или уже удалена.")

        if target.scope in {"substation_id", "urza_id"}:
            owner_id = getattr(record, target.scope)
        elif target.scope == "version":
            parent_id = getattr(record, target.parent_field)
            parent = await self._lock_parent(target, parent_id)
            owner_id = getattr(parent, target.parent_owner_field)
        else:
            parent = await self.session.get(target.parent_model, getattr(record, target.parent_field))
            if parent is None:
                raise LookupError("Документ не найден.")
            owner_id = getattr(parent, target.parent_owner_field)

        allowed = (
            await self.access_service.can_access_substation(user_id, owner_id)
            if target.parent_owner_field == "substation_id" or target.scope == "substation_id"
            else await self.access_service.can_access_urza(user_id, owner_id)
        )
        if not allowed:
            raise PermissionError("Нет доступа к объекту или удаление запрещено.")
        if expected_owner_id is not None and owner_id != expected_owner_id:
            raise LookupError("Запись не найдена в указанном объекте.")

        file_ids = {
            getattr(record, column.name)
            for column in model.__table__.columns
            if any(fk.target_fullname == "files.id" for fk in column.foreign_keys)
            and getattr(record, column.name) is not None
        }
        files = list((await self.session.scalars(select(File).where(File.id.in_(file_ids)))).all()) if file_ids else []
        try:
            await self.session.delete(record)
            await self.session.flush()
            deletable_files = []
            for file in files:
                if not await self.file_owners.get_owners_by_file_id(file.id):
                    await self.session.delete(file)
                    deletable_files.append(file)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            logger.exception("Удаление записи заблокировано ограничением целостности.")
            raise
        except Exception:
            await self.session.rollback()
            logger.exception("Не удалось удалить доменную запись.")
            raise RuntimeError("Не удалось выполнить удаление.") from None

        file_cleanup_failed = False
        for file in deletable_files:
            try:
                await self.storage.delete(key=file.s3_key)
            except Exception:
                file_cleanup_failed = True
                logger.exception("Не удалось удалить бинарный файл после удаления записи.")
        return DeletionResult(owner_id, file_cleanup_failed)

    async def _lock_parent(self, target: DeletionTarget, parent_id: UUID):
        """Блокирует родительскую документную сущность перед удалением версии.

        Args:
            target: Описание типа удаляемой версии.
            parent_id: Идентификатор родительской сущности.

        Returns:
            Заблокированная родительская модель.

        Raises:
            LookupError: Если родительский документ не найден.
        """
        query = (
            select(target.parent_model)
            .where(target.parent_model.id == parent_id)
            .with_for_update()
        )
        parent = await self.session.scalar(query)
        if parent is None:
            raise LookupError("Документ не найден.")
        return parent
