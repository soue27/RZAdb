from datetime import date, datetime, timezone
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


def test_settings_template_links_signed_form_file() -> None:
    file_id = uuid4()
    record = SimpleNamespace(
        change_date=date(2026, 9, 1),
        parameter_name="Параметр",
        initial_setting="1",
        new_setting="2",
        change_reason="Причина",
        creator=SimpleNamespace(full_name="Автор"),
        signed_form_file_id=file_id,
    )

    current_user = SimpleNamespace(
        role=SimpleNamespace(value="engineer"),
    )

    html = templates.get_template("objects/urza_settings.html").render(
        settings_form=object(),
        settings_records=[record],
        current_user=current_user,
    )

    assert "Подписанная форма" in html
    assert_file_actions(html, file_id)

    empty_html = templates.get_template("objects/urza_settings.html").render(
        settings_form=None,
        settings_records=[],
        current_user=current_user,
    )

    assert_no_file_actions(empty_html)


def test_schemas_template_keeps_each_file_role_separate() -> None:
    scan_id, editable_id, signed_id = uuid4(), None, uuid4()
    record = SimpleNamespace(
        schema_number="1",
        schema_name="Схема",
        change_description="Изменение",
        change_justification="Обоснование",
        upload_date=date(2026, 9, 1),
        creator=SimpleNamespace(full_name="Автор"),
        scan_file_id=scan_id,
        editable_file_id=editable_id,
        signed_form_file_id=signed_id,
    )

    html = templates.get_template("objects/urza_schemas.html").render(
        schema_form=object(),
        schema_records=[record],
    )

    assert "Скан" in html
    assert "Редактируемый файл" not in html
    assert "Подписанная форма" in html
    assert_file_actions(html, scan_id)
    assert_file_actions(html, signed_id)
    assert "/files/None/" not in html

    empty_html = templates.get_template("objects/urza_schemas.html").render(
        schema_form=None,
        schema_records=[],
    )
    assert_no_file_actions(empty_html)


def test_maintenance_template_links_protocol_and_signed_form_roles() -> None:
    scan_id, editable_id, signed_id = uuid4(), uuid4(), uuid4()
    record = SimpleNamespace(
        maintenance_date=date(2026, 9, 1),
        maintenance_type=SimpleNamespace(value="В"),
        detected_deviations="—",
        measures_taken="—",
        historical_data=None,
        creator=SimpleNamespace(full_name="Автор"),
        scan_protocol_id=scan_id,
        editable_protocol_id=editable_id,
        signed_form_file_id=signed_id,
    )

    html = templates.get_template("objects/urza_maintenance.html").render(
        maintenance_records=[record],
    )

    assert "Скан протокола" in html
    assert "Редактируемый протокол" in html
    assert "Подписанная форма" in html
    for file_id in (scan_id, editable_id, signed_id):
        assert_file_actions(html, file_id)

    empty_html = templates.get_template("objects/urza_maintenance.html").render(
        maintenance_records=[],
    )
    assert_no_file_actions(empty_html)


def test_programs_template_links_scan_and_optional_editable_file() -> None:
    scan_id = uuid4()
    program = SimpleNamespace(
        program_type=SimpleNamespace(label="Рабочая программа"),
        program_number="1",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        scan_file_id=scan_id,
        editable_file_id=None,
        creator=SimpleNamespace(full_name="Автор"),
    )

    html = templates.get_template("objects/urza_programs.html").render(
        programs=[program],
    )

    assert_file_actions(html, scan_id)
    assert "/files/None/" not in html

    empty_html = templates.get_template("objects/urza_programs.html").render(
        programs=[],
    )
    assert_no_file_actions(empty_html)


def test_instruction_template_links_files_from_selected_version() -> None:
    current_scan_id, selected_scan_id, selected_editable_id = (
        uuid4(),
        uuid4(),
        uuid4(),
    )
    creator = SimpleNamespace(full_name="Автор")
    current_version = SimpleNamespace(
        id=uuid4(),
        version_number=1,
        effective_date=date(2025, 1, 1),
        creator=creator,
        scan_file_id=current_scan_id,
        scan_file=SimpleNamespace(original_name="current.pdf"),
        editable_file_id=None,
        editable_file=None,
    )
    selected_version = SimpleNamespace(
        id=uuid4(),
        version_number=2,
        effective_date=date(2026, 1, 1),
        change_description="Изменение",
        change_justification="Обоснование",
        creator=creator,
        scan_file_id=selected_scan_id,
        scan_file=SimpleNamespace(original_name="selected.pdf"),
        editable_file_id=selected_editable_id,
        editable_file=SimpleNamespace(original_name="selected.docx"),
    )
    instruction = SimpleNamespace(urza_id=uuid4())

    html = templates.get_template("objects/urza_instruction.html").render(
        instruction=instruction,
        versions=[current_version, selected_version],
        selected_version=selected_version,
    )

    assert "Версия 2" in html
    assert_file_actions(html, selected_scan_id)
    assert_file_actions(html, selected_editable_id)
    assert f"/files/{current_scan_id}/view" not in html

    empty_html = templates.get_template("objects/urza_instruction.html").render(
        instruction=None,
        versions=[],
        selected_version=None,
    )
    assert_no_file_actions(empty_html)


def test_common_file_actions_render_icons_text_and_protected_urls() -> None:
    file_id = uuid4()
    macro = templates.get_template("objects/_file_actions.html").module

    html = str(macro.file_actions(file_id))

    assert 'href="/files/' + str(file_id) + '/view"' in html
    assert 'href="/files/' + str(file_id) + '/download"' in html
    assert "visibility" in html
    assert "download" in html
    assert "Просмотр" in html
    assert "Скачать" in html
    assert 'aria-hidden="true"' in html
    assert html.count('class="btn btn-primary"') == 1
    assert html.count('class="btn btn-success"') == 1
    assert "btn-sm" not in html
    assert "btn-outline-primary" not in html
    assert "s3_key" not in html
