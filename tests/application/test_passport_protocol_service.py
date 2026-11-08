from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from docx import Document

from app.application.document_templates.service import (
    DocumentFormHierarchy,
    DocumentTemplateService,
)
from app.application.passport_protocol.service import (
    PassportProtocolNotReadyError,
    PassportProtocolService,
)
from app.domain.enums import DocumentStatus, ElementBase
from app.infrastructure.passport_protocol.zip_exporter import (
    PassportProtocolZipExporter,
)


class FakeOTDService:
    def __init__(self, versions):
        self.versions = versions

    async def get_versions(self, user_id, urza_id):
        return self.versions


class FakeTemplates(DocumentTemplateService):
    def __init__(self, temporary_path=None):
        super().__init__(tree_service=None, templates_dir=Path("data/document_templates"))
        self.temporary_path = temporary_path
        self.temporary_content = (
            temporary_path.read_bytes() if temporary_path is not None else None
        )
        self.requested = []

    async def get_urza_hierarchy(self, user_id, urza_id, *, archive_only=False):
        return DocumentFormHierarchy(
            holding="Холдинг", branch="Филиал", production_department="ПО",
            substation="ПС 1", connection="ВЛ 110", urza="УРОВ 1",
        )

    def create_document(self, form_type, hierarchy):
        self.requested.append(form_type)
        if self.temporary_path:
            self.temporary_path.write_bytes(self.temporary_content)
            return self.temporary_path
        return super().create_document(form_type, hierarchy)


class FakeFileAccess:
    def __init__(self, files):
        self.files = files
        self.calls = []

    async def get_accessible_file(self, *, user_id, file_id):
        self.calls.append((user_id, file_id))
        return self.files[file_id]


class FakeFileService:
    def __init__(self, contents):
        self.contents = contents
        self.read_ids = []

    async def read(self, file):
        self.read_ids.append(file.id)
        return self.contents[file.id]


def _approved_otd(**overrides):
    values = {
        "status": DocumentStatus.APPROVED,
        "panel_cabinet_type": "Шкаф",
        "panel_cabinet_serial": "Ш-12",
        "terminal_type": "Терминал",
        "terminal_serial": "Т-34",
        "terminal_manufacture_year": 2024,
    }
    return SimpleNamespace(**(values | overrides))


def _make_service(*, versions=None, section_records=None, template_service=None):
    urza_id, user_id = uuid4(), uuid4()
    records = section_records or {}
    file_contents = {}
    file_metadata = {}
    for record in records.values():
        if record is not None:
            file_id = record.signed_form_file_id
            file_contents[file_id] = b"%PDF-1.7\n%%EOF"
            file_metadata[file_id] = SimpleNamespace(
                id=file_id,
                extension=".pdf",
            )
    file_access = FakeFileAccess(file_metadata)
    file_service = FakeFileService(file_contents)

    async def get_no_record(*args):
        return None

    async def get_urza(*args):
        return SimpleNamespace(
            dispatch_name="УРОВ 1",
            element_base=ElementBase.MICROPROCESSOR,
            commissioning_date=date(2020, 1, 2),
        )

    service = PassportProtocolService(
        otd_service=FakeOTDService(
            [_approved_otd()] if versions is None else versions
        ),
        settings_service=SimpleNamespace(get_current_approved=get_no_record),
        schema_service=SimpleNamespace(get_current=get_no_record),
        maintenance_service=SimpleNamespace(get_current_approved=get_no_record),
        urza_service=SimpleNamespace(get_details=get_urza),
        document_template_service=template_service or FakeTemplates(),
        file_access_service=file_access,
        file_service=file_service,
    )
    return service, user_id, urza_id, file_access, file_service


@pytest.mark.asyncio
async def test_prepares_four_document_zip_using_latest_approved_otd_and_signed_files():
    approved = _approved_otd()
    newer_draft = _approved_otd(status=DocumentStatus.DRAFT, version_number=99)
    records = {
        "settings": SimpleNamespace(signed_form_file_id=uuid4()),
        "schema": SimpleNamespace(signed_form_file_id=uuid4()),
        "maintenance": SimpleNamespace(signed_form_file_id=uuid4()),
    }
    service, user_id, urza_id, file_access, file_service = _make_service(
        versions=[newer_draft, approved],
        section_records=records,
    )
    async def settings_current(*args):
        return records["settings"]

    async def schema_current(*args):
        return records["schema"]

    async def maintenance_current(*args):
        return records["maintenance"]

    service.settings_service.get_current_approved = settings_current
    service.schema_service.get_current = schema_current
    service.maintenance_service.get_current_approved = maintenance_current

    prepared = await service.prepare(user_id=user_id, urza_id=urza_id)
    archive_bytes = PassportProtocolZipExporter().export(prepared)

    with ZipFile(BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == [
            "01_ОТД.docx", "02_Уставки.pdf", "03_Схемы.pdf", "04_ТО.pdf"
        ]
        assert len(archive.namelist()) == 4
        assert all("/" not in name for name in archive.namelist())
        otd = Document(BytesIO(archive.read("01_ОТД.docx")))
        text = "\n".join(p.text for p in otd.paragraphs)
        assert "УРОВ 1" in text
        assert "Микропроцессорная" in text
        assert "Ш-12" in text
        assert "Т-34" in text
        assert archive.read("02_Уставки.pdf").startswith(b"%PDF-")
        assert archive.read("03_Схемы.pdf").startswith(b"%PDF-")
        assert archive.read("04_ТО.pdf").startswith(b"%PDF-")
    assert len(file_access.calls) == 3
    assert len(file_service.read_ids) == 3


@pytest.mark.asyncio
async def test_empty_approved_sections_use_personalized_docx_templates():
    service, user_id, urza_id, _, _ = _make_service()
    prepared = await service.prepare(user_id=user_id, urza_id=urza_id)
    archive = ZipFile(BytesIO(PassportProtocolZipExporter().export(prepared)))
    assert archive.namelist() == [
        "01_ОТД.docx", "02_Уставки.docx", "03_Схемы.docx", "04_ТО.docx"
    ]
    for name in archive.namelist():
        assert Document(BytesIO(archive.read(name)))


@pytest.mark.asyncio
async def test_missing_approved_otd_stops_package_creation():
    service, user_id, urza_id, _, _ = _make_service(versions=[])
    with pytest.raises(PassportProtocolNotReadyError):
        await service.prepare(user_id=user_id, urza_id=urza_id)


@pytest.mark.asyncio
async def test_incomplete_approved_otd_stops_package_creation():
    service, user_id, urza_id, _, _ = _make_service(
        versions=[_approved_otd(terminal_serial=None)]
    )
    with pytest.raises(PassportProtocolNotReadyError):
        await service.prepare(user_id=user_id, urza_id=urza_id)


@pytest.mark.asyncio
async def test_approved_section_without_signed_file_fails_without_fallback():
    from app.application.passport_protocol.service import PassportProtocolSourceError

    record = SimpleNamespace(signed_form_file_id=None)
    service, user_id, urza_id, _, _ = _make_service()

    async def get_settings(*args):
        return record

    service.settings_service.get_current_approved = get_settings
    with pytest.raises(PassportProtocolSourceError):
        await service.prepare(user_id=user_id, urza_id=urza_id)


def test_zip_exporter_rejects_duplicate_names():
    from app.application.passport_protocol.service import (
        PreparedPassportDocument,
        PreparedPassportProtocol,
    )

    package = PreparedPassportProtocol(tuple(
        PreparedPassportDocument(name, b"content")
        for name in (
            "01_ОТД.docx", "02_Уставки.pdf", "02_Уставки.pdf", "04_ТО.pdf"
        )
    ))
    with pytest.raises(ValueError):
        PassportProtocolZipExporter().export(package)


@pytest.mark.asyncio
async def test_temporary_blank_template_is_removed_after_read(tmp_path):
    path = tmp_path / "temporary.docx"
    Document().save(path)
    template_service = FakeTemplates(temporary_path=path)
    service, user_id, urza_id, _, _ = _make_service(template_service=template_service)
    await service.prepare(user_id=user_id, urza_id=urza_id)
    assert not path.exists()

