from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.application.tree.schemas import EnterpriseTreeNode
from app.application.tree.service import TreeService

logger = logging.getLogger(__name__)


class DocumentFormType(StrEnum):
    """Тип документа Word, который формируется из шаблона.
    """
    MAINTENANCE = "maintenance"
    SETTINGS = "settings"
    SCHEMES = "schemes"


@dataclass(frozen=True)
class DocumentFormHierarchy:
    """Иерархические наименования объектов, подставляемые в маркеры DOCX-шаблона.
    """
    holding: str = ""
    branch: str = ""
    production_department: str = ""
    substation: str = ""
    connection: str = ""
    urza: str = ""

    def marker_values(self) -> dict[str, str]:
        """Возвращает соответствие маркеров шаблона значениям из иерархии.

        Returns:
            Словарь маркер → текст для подстановки в документ.
        """
        return {
            "$холдинг": self.holding,
            "$филиал": self.branch,
            "$Название Производственного отделения": self.production_department,
            "$Название подстанции": self.substation,
            "$Название присоединения": self.connection,
            "$Название УРЗА": self.urza,
        }


class DocumentTemplateError(Exception):
    """Runtime DOCX-шаблон отсутствует или имеет некорректный формат."""


class DocxProcessor:
    """Заменяет известные маркеры, сохраняя форматирование окружающих фрагментов текста."""

    @staticmethod
    def replace_markers(document, values: dict[str, str]) -> None:
        """Заменяет известные маркеры во всех абзацах документа.

        Проверяет, что каждый обязательный маркер найден и после обработки
        в документе не осталось его незаменённых вхождений.

        Args:
            document: Открытый DOCX-документ.
            values: Словарь маркеров и значений для подстановки.

        Raises:
            DocumentTemplateError: Если обязательные маркеры отсутствуют или остались в документе.
        """
        required = set(values)
        found: set[str] = set()
        paragraphs = list(DocxProcessor._document_paragraphs(document))

        for paragraph in paragraphs:
            found.update(DocxProcessor._replace_in_paragraph(paragraph, values))

        missing = required - found
        if missing:
            raise DocumentTemplateError(
                "Runtime DOCX template is missing required markers: "
                + ", ".join(sorted(missing))
            )

        leftovers = {
            marker
            for paragraph in paragraphs
            for marker in values
            if marker in paragraph.text
        }
        if leftovers:
            raise DocumentTemplateError(
                "Unreplaced markers remain in generated DOCX: "
                + ", ".join(sorted(leftovers))
            )

    @staticmethod
    def _document_paragraphs(document):
        """Обходит абзацы документа, включая вложенные таблицы и контейнеры DOCX.

        Args:
            document: Открытый DOCX-документ.

        Yields:
            Абзацы документа без повторного обхода одного контейнера.
        """
        visited_containers: set[int] = set()

        def visit(container):
            container_element = container._element
            if id(container_element) in visited_containers:
                return
            visited_containers.add(id(container_element))
            yield from container.paragraphs
            for table in container.tables:
                yield from visit_table(table)

        def visit_table(table: Table):
            for row in table.rows:
                for cell in row.cells:
                    yield from visit(cell)

        yield from visit(document)
        for section in document.sections:
            for name in (
                "header", "first_page_header", "even_page_header",
                "footer", "first_page_footer", "even_page_footer",
            ):
                yield from visit(getattr(section, name))

    @staticmethod
    def _replace_in_paragraph(
        paragraph: Paragraph,
        values: dict[str, str],
    ) -> set[str]:
        """Заменяет маркеры внутри абзаца с сохранением форматирования runs.

        Args:
            paragraph: Обрабатываемый абзац.
            values: Словарь маркеров и значений.

        Returns:
            Множество маркеров, найденных и заменённых в абзаце.
        """
        runs = paragraph.runs
        if not runs:
            return set()
        text = "".join(run.text for run in runs)
        if not text:
            return set()

        offsets: list[tuple[int, int]] = []
        position = 0
        for run in runs:
            end = position + len(run.text)
            offsets.append((position, end))
            position = end

        output = [""] * len(runs)
        found: set[str] = set()
        markers = tuple(values)
        position = 0
        while position < len(text):
            marker = next(
                (candidate for candidate in markers if text.startswith(candidate, position)),
                None,
            )
            run_index = next(
                (
                    index for index, (start, end) in enumerate(offsets)
                    if start <= position < end
                ),
                len(runs) - 1,
            )
            if marker is not None:
                output[run_index] += values[marker] or ""
                found.add(marker)
                position += len(marker)
            else:
                output[run_index] += text[position]
                position += 1

        for run, replacement in zip(runs, output, strict=True):
            run.text = replacement
        return found


class DocumentTemplateService:
    """Готовит DOCX-документы из runtime-шаблонов и данных иерархии РЗА.
    """
    def __init__(
        self,
        tree_service: TreeService,
        templates_dir: Path,
    ) -> None:
        """Сохраняет сервис дерева и каталог runtime-шаблонов.

        Args:
            tree_service: Сервис получения иерархии объектов.
            templates_dir: Каталог файлов DOCX-шаблонов.
        """
        self.tree_service = tree_service
        self.templates_dir = templates_dir

    @staticmethod
    def download_filename(
        form_type: DocumentFormType,
        hierarchy: DocumentFormHierarchy,
    ) -> str:
        """Формирует имя файла для скачивания с учётом типа документа и объекта.

        Args:
            form_type: Тип формируемого документа.
            hierarchy: Наименования объектов иерархии.

        Returns:
            Безопасное имя DOCX-файла.
        """
        labels = {
            DocumentFormType.MAINTENANCE: "ТО",
            DocumentFormType.SETTINGS: "уставок",
            DocumentFormType.SCHEMES: "схем",
        }
        object_name = "_".join(
            value for value in (hierarchy.substation, hierarchy.connection) if value
        ) or "объект"
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", object_name)
        safe_name = re.sub(r"\s+", "_", safe_name).strip("._ ") or "объект"
        return f"Формуляр_{labels[form_type]}_{safe_name}.docx"

    async def get_urza_hierarchy(
        self,
        user_id: UUID,
        urza_id: UUID,
        *,
        archive_only: bool = False,
    ) -> DocumentFormHierarchy:
        """Получает иерархию УРЗА для подстановки в документ.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.
            archive_only: Разрешает использовать архивный объект при подготовке документа.

        Returns:
            Наименования холдинга, филиала, отделения, подстанции, присоединения и УРЗА.

        Raises:
            DocumentTemplateError: Если иерархию невозможно определить.
        """
        tree = await self.tree_service.get_tree(
            user_id=user_id,
            archive_only=archive_only,
        )

        def visit(
            node: EnterpriseTreeNode,
            parent_path: list,
        ) -> DocumentFormHierarchy | None:
            ancestry = node.ancestors or parent_path
            path = [*ancestry, node]
            names = {
                item.type: item.full_name
                for item in path
                if item.type in {"holding", "branch", "department"}
            }
            for station in node.substations:
                for connection in station.connections:
                    for urza in connection.urzas:
                        if urza.id == urza_id:
                            return DocumentFormHierarchy(
                                holding=names.get("holding", ""),
                                branch=names.get("branch", ""),
                                production_department=names.get("department", ""),
                                substation=station.dispatch_name,
                                connection=connection.dispatch_name,
                                urza=urza.dispatch_name,
                            )
            for child in node.children:
                result = visit(child, path)
                if result is not None:
                    return result
            return None

        for root in tree:
            result = visit(root, [])
            if result is not None:
                return result
        return DocumentFormHierarchy()

    def create_document(
        self,
        form_type: DocumentFormType,
        hierarchy: DocumentFormHierarchy,
    ) -> Path:
        """Создаёт DOCX-файл из шаблона, подставляя маркеры иерархии.

        Args:
            form_type: Тип документа.
            hierarchy: Значения иерархии для заполнения шаблона.

        Returns:
            Путь к временному сформированному DOCX-файлу.

        Raises:
            DocumentTemplateError: Если шаблон отсутствует, некорректен или содержит незаполненные маркеры.
        """
        template_path = self.templates_dir / f"{form_type.value}.docx"
        if not template_path.is_file():
            raise DocumentTemplateError(f"DOCX template not found: {template_path}")

        output_path: Path | None = None
        try:
            document = Document(template_path)
            DocxProcessor.replace_markers(document, hierarchy.marker_values())
            with tempfile.NamedTemporaryFile(
                prefix=f"rzadb-{form_type.value}-",
                suffix=".docx",
                delete=False,
            ) as temporary:
                output_path = Path(temporary.name)
            document.save(output_path)
            return output_path
        except DocumentTemplateError:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            logger.exception("Failed to process DOCX template %s", template_path)
            raise DocumentTemplateError("DOCX template could not be processed") from exc
