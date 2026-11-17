from hashlib import sha256
from pathlib import Path

from app.infrastructure.document_templates.catalog import DocumentTemplateCatalog


def test_source_templates_have_one_canonical_location() -> None:
    catalog = DocumentTemplateCatalog()
    expected = {
        "urza/OTD.docx",
        "urza/maintenance.docx",
        "urza/schemes.docx",
        "urza/settings.docx",
        "inspections/Шаблон_осмотра_подстанции.docx",
    }
    actual = {
        path.relative_to(catalog.root).as_posix()
        for path in catalog.root.rglob("*.docx")
    }

    assert actual == expected
    assert list(Path("docs").rglob("*.docx")) == []
    assert list(Path("data/document_templates").rglob("*.docx")) == []
    assert catalog.legacy_inspection_pdf.is_file()


def test_source_docx_templates_are_not_duplicate_copies() -> None:
    catalog = DocumentTemplateCatalog()
    files = list(catalog.root.rglob("*.docx"))
    checksums = [sha256(path.read_bytes()).hexdigest() for path in files]

    assert len(checksums) == len(set(checksums))


def test_catalog_uses_configured_root(tmp_path: Path) -> None:
    catalog = DocumentTemplateCatalog(root=tmp_path)

    assert catalog.urza_directory == tmp_path / "urza"
    assert catalog.otd == tmp_path / "urza" / "OTD.docx"
    assert catalog.inspection == (
        tmp_path / "inspections" / "Шаблон_осмотра_подстанции.docx"
    )
