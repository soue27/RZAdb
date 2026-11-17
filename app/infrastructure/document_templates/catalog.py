from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentTemplateCatalog:
    """Central paths for source templates shipped with the application."""

    root: Path = Path("app/infrastructure/document_templates")

    @property
    def urza_directory(self) -> Path:
        return self.root / "urza"

    @property
    def otd(self) -> Path:
        return self.urza_directory / "OTD.docx"

    @property
    def inspection(self) -> Path:
        return self.root / "inspections" / "Шаблон_осмотра_подстанции.docx"

    @property
    def legacy_inspection_pdf(self) -> Path:
        return self.root / "inspections" / "legacy" / "inspection_template.pdf"
