from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/presentation/templates")


def assert_file_actions(html: str, file_id) -> None:
    assert f'href="/files/{file_id}/view"' in html
    assert f'href="/files/{file_id}/download"' in html


def assert_no_file_actions(html: str) -> None:
    assert "/files/" not in html
    assert "rzadb-file-actions" not in html


def test_inspection_template_links_each_present_file_role() -> None:
    scan_id, editable_id = uuid4(), uuid4()
    inspections = [
        SimpleNamespace(
            inspection_date=date(2026, 9, 1),
            remarks="Скан осмотра",
            scan_file_id=scan_id,
            scan_file_name="scan.pdf",
            editable_file_id=None,
            editable_file_name=None,
        ),
        SimpleNamespace(
            inspection_date=date(2026, 8, 1),
            remarks="Редактируемый результат",
            scan_file_id=None,
            scan_file_name=None,
            editable_file_id=editable_id,
            editable_file_name="inspection.docx",
        ),
        SimpleNamespace(
            inspection_date=date(2026, 7, 1),
            remarks="Без файлов",
            scan_file_id=None,
            scan_file_name=None,
            editable_file_id=None,
            editable_file_name=None,
        ),
    ]

    html = templates.get_template(
        "objects/substation_inspections.html",
    ).render(inspections=inspections)

    assert_file_actions(html, scan_id)
    assert_file_actions(html, editable_id)
    assert "scan.pdf" in html
    assert "inspection.docx" in html
    assert "/files/None/" not in html
    assert html.count('class="rzadb-file-actions"') == 2

    empty_html = templates.get_template(
        "objects/substation_inspections.html",
    ).render(inspections=[])
    assert_no_file_actions(empty_html)


def test_instruction_template_links_current_version_files() -> None:
    scan_id, editable_id = uuid4(), uuid4()
    current_instruction = SimpleNamespace(
        version_number=3,
        effective_date=date(2026, 1, 1),
        change_description="Изменение",
        change_justification="Обоснование",
        scan_file_id=scan_id,
        scan_file_name="instruction.pdf",
        editable_file_id=editable_id,
        editable_file_name="instruction.docx",
    )

    html = templates.get_template(
        "objects/substation_instructions.html",
    ).render(instruction=current_instruction)

    assert "Версия 3" in html
    assert_file_actions(html, scan_id)
    assert_file_actions(html, editable_id)
    assert "instruction.pdf" in html
    assert "instruction.docx" in html

    current_instruction.editable_file_id = None
    current_instruction.editable_file_name = None
    html_without_editable = templates.get_template(
        "objects/substation_instructions.html",
    ).render(instruction=current_instruction)
    assert_file_actions(html_without_editable, scan_id)
    assert html_without_editable.count('class="rzadb-file-actions"') == 1
    assert "/files/None/" not in html_without_editable

    empty_html = templates.get_template(
        "objects/substation_instructions.html",
    ).render(instruction=None)
    assert_no_file_actions(empty_html)


def test_selectivity_template_uses_file_ids_per_version() -> None:
    first_scan_id, first_editable_id, second_scan_id = (
        uuid4(),
        uuid4(),
        uuid4(),
    )
    versions = [
        SimpleNamespace(
            version_number=2,
            effective_date=date(2026, 1, 1),
            number="2",
            name="Актуальная схема",
            change_description="Новое изменение",
            creator_name="Автор 2",
            scan_file_id=first_scan_id,
            scan_file_name="scheme-2.pdf",
            editable_file_id=first_editable_id,
            editable_file_name="scheme-2.dwg",
        ),
        SimpleNamespace(
            version_number=1,
            effective_date=date(2025, 1, 1),
            number="1",
            name="Первая схема",
            change_description=None,
            creator_name="Автор 1",
            scan_file_id=second_scan_id,
            scan_file_name="scheme-1.pdf",
            editable_file_id=None,
            editable_file_name=None,
        ),
    ]

    html = templates.get_template(
        "objects/substation_selectivity_schemes.html",
    ).render(versions=versions)

    for file_id in (first_scan_id, first_editable_id, second_scan_id):
        assert_file_actions(html, file_id)
    assert html.count('class="rzadb-file-actions"') == 3
    assert "/files/None/" not in html

    empty_html = templates.get_template(
        "objects/substation_selectivity_schemes.html",
    ).render(versions=[])
    assert_no_file_actions(empty_html)
