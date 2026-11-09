from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from docx import Document

from app.application.document_templates.service import (
    DocxProcessor,
    DocumentFormHierarchy,
    DocumentFormType,
    DocumentTemplateError,
    DocumentTemplateService,
)
from app.application.files.access_service import FileAccessService
from app.application.files.service import FileService
from app.application.files.validation import MIME_TYPES_BY_EXTENSION
from app.application.maintenance.service import TORecordService
from app.application.otd.service import OTDService
from app.application.schema.service import SchemaService
from app.application.settings.service import SettingsService
from app.application.urzas.service import URZAService
from app.domain.enums import DocumentStatus

logger = logging.getLogger(__name__)


class PassportProtocolNotReadyError(Exception):
    """Утверждённый проект ОТД отсутствует или заполнен не полностью."""


class PassportProtocolSourceError(Exception):
    """Обязательный исходный документ отсутствует или не может быть прочитан."""


@dataclass(frozen=True)
class PreparedPassportDocument:
    """Имя и бинарное содержимое одного подготовленного документа паспорта.
    """
    filename: str
    content: bytes


@dataclass(frozen=True)
class PreparedPassportProtocol:
    """Набор документов, подготовленных для выдачи паспорта УРЗА.
    """
    documents: tuple[PreparedPassportDocument, ...]


class PassportProtocolService:
    """Собирает документы ОТД, уставок, схем и ТО в комплект паспорта УРЗА.
    """
    def __init__(
        self,
        *,
        otd_service: OTDService,
        settings_service: SettingsService,
        schema_service: SchemaService,
        maintenance_service: TORecordService,
        urza_service: URZAService,
        document_template_service: DocumentTemplateService,
        file_access_service: FileAccessService,
        file_service: FileService,
        otd_template_path: Path = Path("docs/OTD.docx"),
    ) -> None:
        """Сохраняет сервисы документов, файлов и шаблонов, необходимые для сборки паспорта.

        Args:
            otd_service: Сервис формуляра ОТД.
            settings_service: Сервис уставок.
            schema_service: Сервис схем.
            maintenance_service: Сервис технического обслуживания.
            urza_service: Сервис устройств РЗА.
            document_template_service: Сервис DOCX-шаблонов.
            file_access_service: Сервис проверки доступа к исходным файлам.
            file_service: Сервис чтения бинарного содержимого.
            otd_template_path: Путь к шаблону титульного/основного документа ОТД.
        """
        self.otd_service = otd_service
        self.settings_service = settings_service
        self.schema_service = schema_service
        self.maintenance_service = maintenance_service
        self.urza_service = urza_service
        self.document_template_service = document_template_service
        self.file_access_service = file_access_service
        self.file_service = file_service
        self.otd_template_path = otd_template_path

    async def prepare(
        self,
        *,
        user_id: UUID,
        urza_id: UUID,
    ) -> PreparedPassportProtocol:
        """Подготавливает комплект документов паспорта указанного УРЗА.

        Проверяет доступ пользователя, получает утверждённые и связанные документы,
        формирует DOCX и собирает бинарные вложения в единый результат.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Набор подготовленных документов с именами и содержимым.

        Raises:
            PassportProtocolNotReadyError: Если обязательный утверждённый проект ОТД отсутствует.
            PassportProtocolSourceError: Если исходный документ отсутствует или не читается.
        """
        versions = await self.otd_service.get_versions(user_id, urza_id)
        approved_otd = next(
            (version for version in versions if version.status is DocumentStatus.APPROVED),
            None,
        )
        if approved_otd is None:
            raise PassportProtocolNotReadyError

        missing_fields = [
            name
            for name, value in (
                ("тип панели/шкафа", approved_otd.panel_cabinet_type),
                ("заводской номер панели/шкафа", approved_otd.panel_cabinet_serial),
                ("тип терминала", approved_otd.terminal_type),
                ("заводской номер терминала", approved_otd.terminal_serial),
                ("год изготовления терминала", approved_otd.terminal_manufacture_year),
            )
            if value is None or (isinstance(value, str) and not value.strip())
        ]
        if missing_fields:
            logger.warning(
                "Approved OTD version for URZA %s is missing title fields: %s",
                urza_id,
                ", ".join(missing_fields),
            )
            raise PassportProtocolNotReadyError

        hierarchy = await self.document_template_service.get_urza_hierarchy(
            user_id,
            urza_id,
        )
        urza = await self.urza_service.get_details(urza_id)
        otd_bytes = self._prepare_otd(approved_otd, hierarchy, urza)

        settings = await self.settings_service.get_current_approved(user_id, urza_id)
        schema = await self.schema_service.get_current(user_id, urza_id)
        maintenance = await self.maintenance_service.get_current_approved(
            user_id,
            urza_id,
        )

        documents = [PreparedPassportDocument("01_ОТД.docx", otd_bytes)]
        documents.append(await self._prepare_section(
            "02_Уставки", DocumentFormType.SETTINGS, settings, hierarchy, user_id
        ))
        documents.append(await self._prepare_section(
            "03_Схемы", DocumentFormType.SCHEMES, schema, hierarchy, user_id
        ))
        documents.append(await self._prepare_section(
            "04_ТО", DocumentFormType.MAINTENANCE, maintenance, hierarchy, user_id
        ))
        return PreparedPassportProtocol(tuple(documents))

    def _prepare_otd(self, version, hierarchy, urza) -> bytes:
        """Формирует DOCX-документ ОТД на основе утверждённой версии и иерархии УРЗА.

        Args:
            version: Утверждённая версия ОТД.
            hierarchy: Наименования объектов иерархии.
            urza: Устройство, для которого формируется паспорт.

        Returns:
            Бинарное содержимое сформированного DOCX.
        """
        values = {
            "$Холдинг": hierarchy.holding,
            "$Филиал": hierarchy.branch,
            "$Название производственного отделения": hierarchy.production_department,
            "$Название подстанции": hierarchy.substation,
            "$Название присоединения": hierarchy.connection,
            "$URZA. dispatch_name": urza.dispatch_name,
            "$URZA.element_base": urza.element_base.label,
            "$panel_cabinet_type": version.panel_cabinet_type or "",
            "$panel_cabinet_serial": version.panel_cabinet_serial or "",
            "$terminal_type": version.terminal_type or "",
            "$terminal_serial": version.terminal_serial or "",
            "$terminal_manufacture_year": (
                str(version.terminal_manufacture_year)
                if version.terminal_manufacture_year is not None
                else ""
            ),
            "$URZA.commissioning_date": urza.commissioning_date.strftime("%d.%m.%Y"),
        }
        try:
            document = Document(self.otd_template_path)
            DocxProcessor.replace_markers(document, values)
            output = BytesIO()
            document.save(output)
            return output.getvalue()
        except DocumentTemplateError as exc:
            logger.exception("OTD passport template is missing required markers")
            raise PassportProtocolSourceError from exc
        except Exception as exc:
            logger.exception("Could not prepare OTD passport template")
            raise PassportProtocolSourceError from exc

    async def _prepare_section(
        self,
        base_filename: str,
        form_type: DocumentFormType,
        record,
        hierarchy: DocumentFormHierarchy,
        user_id: UUID,
    ) -> PreparedPassportDocument:
        """Подготавливает документный раздел паспорта из записи и её файла.

        Args:
            base_filename: Базовое имя результирующего файла.
            form_type: Тип документа для выбора шаблона.
            record: Утверждённая запись документа.
            hierarchy: Иерархические наименования для шаблона.
            user_id: Идентификатор пользователя, от имени которого читается файл.

        Returns:
            Подготовленный документ с именем и бинарным содержимым.

        Raises:
            PassportProtocolSourceError: Если требуемый исходный файл отсутствует или не читается.
        """
        if record is None:
            temporary_path: Path | None = None
            try:
                temporary_path = self.document_template_service.create_document(
                    form_type,
                    hierarchy,
                )
                content = temporary_path.read_bytes()
            except Exception as exc:
                logger.exception("Could not prepare blank passport section %s", form_type)
                raise PassportProtocolSourceError from exc
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            return PreparedPassportDocument(f"{base_filename}.docx", content)

        file_id = getattr(record, "signed_form_file_id", None)
        if file_id is None:
            logger.error(
                "Approved passport section %s has no signed form file",
                form_type,
            )
            raise PassportProtocolSourceError
        try:
            source_file = await self.file_access_service.get_accessible_file(
                user_id=user_id,
                file_id=file_id,
            )
            content = await self.file_service.read(source_file)
        except Exception as exc:
            logger.exception("Could not read signed passport section %s", form_type)
            raise PassportProtocolSourceError from exc
        extension = str(source_file.extension).lower().lstrip(".")
        if f".{extension}" not in MIME_TYPES_BY_EXTENSION:
            logger.error(
                "Unsupported signed form extension for passport section %s",
                form_type,
            )
            raise PassportProtocolSourceError
        if not content:
            logger.error("Signed passport section %s is empty", form_type)
            raise PassportProtocolSourceError
        try:
            if extension == "pdf" and not content.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF signature")
            if extension in {"docx", "xlsx", "odt", "ods", "vsdx", "dwfx", "odg"}:
                with ZipFile(BytesIO(content)) as source_archive:
                    damaged_member = source_archive.testzip()
                    if damaged_member is not None:
                        raise BadZipFile("Damaged office document archive")
        except (BadZipFile, ValueError) as exc:
            logger.exception("Signed passport section %s is damaged", form_type)
            raise PassportProtocolSourceError from exc
        return PreparedPassportDocument(f"{base_filename}.{extension}", content)
