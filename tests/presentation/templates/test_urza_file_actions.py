from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid6 import uuid7

from fastapi.templating import Jinja2Templates

from app.domain.enums import DocumentStatus

templates = Jinja2Templates(directory="app/presentation/templates")


def assert_file_actions(html: str, file_id) -> None:
    assert f'href="/files/{file_id}/view"' in html
    assert f'href="/files/{file_id}/download"' in html


def assert_no_file_actions(html: str) -> None:
    assert "/files/" not in html
    assert "rzadb-file-actions" not in html


def test_settings_template_links_signed_form_file() -> None:
    file_id = uuid7()
    record_id = uuid7()
    record = SimpleNamespace(
        id=record_id,
        change_date=date(2026, 9, 1),
        parameter_name="Параметр",
        initial_setting="1",
        new_setting="2",
        change_reason="Причина",
        status=DocumentStatus.DRAFT,
        creator=SimpleNamespace(full_name="Автор"),
        signed_form_file_id=file_id,
    )

    current_user = SimpleNamespace(
        role=SimpleNamespace(value="engineer"),
    )

    html = templates.get_template("objects/urza_settings.html").render(
        urza_id=uuid7(),
        settings_form=object(),
        settings_records=[record],
        current_approved=None,
        actions_by_record={record_id: {"edit", "submit"}},
        current_user=current_user,
    )

    assert "Подписанный формуляр" in html
    assert "Черновик" in html
    assert "Изменить" in html
    assert "Направить на согласование" in html
    assert "Удалить" not in html
    assert_file_actions(html, file_id)

    empty_html = templates.get_template("objects/urza_settings.html").render(
        urza_id=uuid7(),
        settings_form=None,
        settings_records=[],
        current_approved=None,
        actions_by_record={},
        current_user=current_user,
    )

    assert_no_file_actions(empty_html)


def test_settings_template_shows_current_approved_and_available_actions():
    approved_id, review_id, file_id = uuid7(), uuid7(), uuid7()
    approved = SimpleNamespace(
        id=approved_id,
        change_date=date(2026, 9, 1),
        parameter_name="Текущая уставка",
        initial_setting="1",
        new_setting="2",
        change_reason="Причина",
        status=DocumentStatus.APPROVED,
        creator=SimpleNamespace(full_name="Автор"),
        signed_form_file_id=file_id,
    )
    under_review = SimpleNamespace(
        id=review_id,
        change_date=date(2026, 9, 2),
        parameter_name="На проверке",
        initial_setting="2",
        new_setting="3",
        change_reason="Причина",
        status=DocumentStatus.UNDER_REVIEW,
        creator=SimpleNamespace(full_name="Автор"),
        signed_form_file_id=uuid7(),
    )
    manager = SimpleNamespace(role=SimpleNamespace(value="manager"))
    html = templates.get_template("objects/urza_settings.html").render(
        urza_id=uuid7(),
        settings_records=[under_review, approved],
        current_approved=approved,
        actions_by_record={review_id: {"approve", "return"}, approved_id: set()},
        current_user=manager,
    )

    assert "Текущие уставки" in html
    assert "На согласовании" in html
    assert "Утвердить" in html
    assert "Вернуть в черновик" in html
    assert "Изменить" not in html
    assert "Направить на согласование" not in html
    assert "Удалить" not in html
    assert_file_actions(html, file_id)


def test_settings_template_shows_delete_only_when_action_is_available():
    record_id = uuid7()
    record = SimpleNamespace(
        id=record_id,
        change_date=date(2026, 9, 1),
        parameter_name="Параметр",
        initial_setting="1",
        new_setting="2",
        change_reason="Причина",
        status=DocumentStatus.APPROVED,
        creator=None,
        signed_form_file_id=None,
    )
    admin = SimpleNamespace(role=SimpleNamespace(value="admin"))
    html = templates.get_template("objects/urza_settings.html").render(
        urza_id=uuid7(),
        settings_records=[record],
        current_approved=record,
        actions_by_record={record_id: {"delete"}},
        current_user=admin,
    )
    assert "Текущие уставки" in html
    assert "Удалить" in html
    assert "Изменить" not in html
    assert "Утвердить" not in html


def test_settings_form_create_and_edit_modes():
    template = templates.get_template("objects/urza_settings_form.html")
    urza_id = uuid7()
    create_html = template.render(
        urza_id=urza_id,
        is_edit=False,
        record=None,
        form_values={},
        error_message=None,
    )
    assert 'name="signed_form_file"' in create_html
    assert 'name="signed_form_file"' in create_html
    assert 'type="file"' in create_html
    assert "required" in create_html
    assert "Ток срабатывания" not in create_html

    file_id = uuid7()
    record = SimpleNamespace(
        id=uuid7(),
        change_date=date(2026, 9, 1),
        parameter_name="Ток срабатывания",
        initial_setting="1",
        new_setting="2",
        change_reason="Причина",
        signed_form_file_id=file_id,
    )
    edit_html = template.render(
        urza_id=urza_id,
        is_edit=True,
        record=record,
        form_values={},
        error_message="Ошибка проверки",
    )
    assert "Ток срабатывания" in edit_html
    assert "Ошибка проверки" in edit_html
    assert "Если новый файл не выбран" in edit_html
    assert_file_actions(edit_html, file_id)


def test_schemas_template_keeps_each_file_role_separate() -> None:
    scan_id, editable_id, signed_id = uuid7(), None, uuid7()

    record = SimpleNamespace(
        id=uuid7(),
        schema_number="1",
        schema_name="Схема",
        change_description="Изменение",
        change_justification="Обоснование",
        upload_date=date(2026, 9, 1),
        status=DocumentStatus.APPROVED,
        deleted_at=None,
        creator=SimpleNamespace(full_name="Автор"),
        scan_file_id=scan_id,
        editable_file_id=editable_id,
        signed_form_file_id=signed_id,
    )

    current_user = SimpleNamespace(
        role=SimpleNamespace(value="engineer"),
    )

    html = templates.get_template("objects/urza_schemas.html").render(
        urza_id=uuid7(),
        schema_form=object(),
        schema_records=[record],
        current_record=record,
        schema_actions={record.id: {"new_record"}},
        current_user=current_user,
    )

    assert "Скан схемы" in html
    assert "Редактируемый файл" not in html
    assert "Подписанный формуляр" in html
    assert "Текущая" in html
    assert "Утверждено" in html
    assert "Изменить" not in html
    assert "Новое изменение" in html
    assert_file_actions(html, scan_id)
    assert_file_actions(html, signed_id)
    assert "/files/None/" not in html

    empty_html = templates.get_template("objects/urza_schemas.html").render(
        urza_id=uuid7(),
        schema_form=None,
        schema_records=[],
        current_record=None,
        schema_actions={},
        current_user=current_user,
    )

    assert_no_file_actions(empty_html)


def test_schemes_template_shows_only_available_workflow_and_delete_actions():
    urza_id = uuid7()
    draft, review, approved = [
        SimpleNamespace(
            id=uuid7(),
            schema_number=f"SC-{index}",
            schema_name=f"Схема {index}",
            change_description="Изменение",
            change_justification="Обоснование",
            upload_date=date(2026, 9, index),
            status=status,
            creator=SimpleNamespace(full_name="Автор"),
            scan_file_id=None,
            editable_file_id=None,
            signed_form_file_id=uuid7(),
            deleted_at=None,
        )
        for index, status in enumerate(
            [
                DocumentStatus.DRAFT,
                DocumentStatus.UNDER_REVIEW,
                DocumentStatus.APPROVED,
            ],
            start=1,
        )
    ]
    html = templates.get_template("objects/urza_schemas.html").render(
        urza_id=urza_id,
        schema_form=object(),
        schema_records=[draft, review, approved],
        current_record=approved,
        schema_actions={
            draft.id: {"edit", "submit", "delete"},
            review.id: {"approve", "return"},
            approved.id: {"new_record"},
        },
        current_user=SimpleNamespace(role=SimpleNamespace(value="admin")),
    )

    assert "Направить на согласование" in html
    assert "Утвердить" in html
    assert "Вернуть на доработку" in html
    assert html.count("Изменить") == 1
    assert html.count(">Удалить</button>") == 1
    assert "Новое изменение" in html


def test_schemes_form_create_and_edit_modes_keep_file_rules():
    template = templates.get_template("objects/urza_schemas_form.html")
    urza_id, task_id, signed_id = uuid7(), uuid7(), uuid7()
    create_html = template.render(
        urza_id=urza_id,
        record=None,
        task_id=task_id,
        form_values={},
        error_message=None,
        is_edit=False,
    )
    assert 'name="signed_form_file"' in create_html
    assert 'id="signed_form_file"' in create_html
    assert 'name="scan_file"' in create_html
    assert 'name="editable_file"' in create_html
    assert 'name="task_id"' in create_html
    assert "required" in create_html

    record = SimpleNamespace(
        id=uuid7(),
        task_id=task_id,
        schema_number="SC-1",
        schema_name="Схема",
        change_description="Изменение",
        change_justification="Причина",
        upload_date=date(2026, 9, 1),
        signed_form_file_id=signed_id,
        scan_file_id=None,
        editable_file_id=None,
    )
    edit_html = template.render(
        urza_id=urza_id,
        record=record,
        task_id=task_id,
        form_values={},
        error_message="Ошибка сохранения",
        is_edit=True,
    )
    assert "Схема" in edit_html
    assert "Ошибка сохранения" in edit_html
    assert "Текущий подписанный формуляр" in edit_html
    assert "Если новый файл не выбран" in edit_html
    assert_file_actions(edit_html, signed_id)


def test_maintenance_template_links_protocol_and_signed_form_roles() -> None:
    scan_id, editable_id, signed_id = uuid7(), uuid7(), uuid7()
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
    scan_id = uuid7()
    program = SimpleNamespace(
        id=uuid7(),
        program_type=SimpleNamespace(label="Рабочая программа"),
        program_number="1",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        status=DocumentStatus.DRAFT,
        scan_file_id=scan_id,
        editable_file_id=None,
        creator=SimpleNamespace(full_name="Автор"),
    )

    html = templates.get_template("objects/urza_programs.html").render(
        urza_id=uuid7(),
        programs=[program],
        program_actions={program.id: {"submit"}},
    )

    assert_file_actions(html, scan_id)
    assert "/files/None/" not in html

    empty_html = templates.get_template("objects/urza_programs.html").render(
        urza_id=uuid7(),
        programs=[],
        program_actions={},
    )
    assert_no_file_actions(empty_html)


def test_programs_template_shows_submit_action_for_draft() -> None:
    program = SimpleNamespace(
        id=uuid7(),
        program_type=SimpleNamespace(label="Рабочая программа"),
        program_number="1",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        creator=SimpleNamespace(full_name="Автор"),
    )

    html = templates.get_template("objects/urza_programs.html").render(
        urza_id=uuid7(),
        programs=[program],
        program_actions={program.id: {"submit"}},
    )

    assert "Черновик" in html
    assert "Направить на согласование" in html
    assert "Утвердить" not in html
    assert "Вернуть на доработку" not in html


def test_programs_template_shows_review_actions() -> None:
    program = SimpleNamespace(
        id=uuid7(),
        program_type=SimpleNamespace(label="Рабочая программа"),
        program_number="1",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        status=DocumentStatus.UNDER_REVIEW,
        scan_file_id=uuid7(),
        editable_file_id=None,
        creator=SimpleNamespace(full_name="Автор"),
    )

    html = templates.get_template("objects/urza_programs.html").render(
        urza_id=uuid7(),
        programs=[program],
        program_actions={program.id: {"approve", "return"}},
    )

    assert "На согласовании" in html
    assert "Утвердить" in html
    assert "Вернуть на доработку" in html
    assert "Направить на согласование" not in html


def test_programs_template_hides_workflow_actions_for_approved() -> None:
    program = SimpleNamespace(
        id=uuid7(),
        program_type=SimpleNamespace(label="Рабочая программа"),
        program_number="1",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        status=DocumentStatus.APPROVED,
        scan_file_id=uuid7(),
        editable_file_id=None,
        creator=SimpleNamespace(full_name="Автор"),
    )

    html = templates.get_template("objects/urza_programs.html").render(
        urza_id=uuid7(),
        programs=[program],
        program_actions={program.id: set()},
    )

    assert "Утверждено" in html
    assert "Направить на согласование" not in html
    assert "Утвердить" not in html
    assert "Вернуть на доработку" not in html

def test_instruction_template_links_files_from_selected_version() -> None:
    current_scan_id, selected_scan_id, selected_editable_id = (
        uuid7(),
        uuid7(),
        uuid7(),
    )
    creator = SimpleNamespace(full_name="Автор")
    current_version = SimpleNamespace(
        id=uuid7(),
        version_number=1,
        status=DocumentStatus.APPROVED,
        effective_date=date(2025, 1, 1),
        creator=creator,
        scan_file_id=current_scan_id,
        scan_file=SimpleNamespace(original_name="current.pdf"),
        editable_file_id=None,
        editable_file=None,
    )
    selected_version = SimpleNamespace(
        id=uuid7(),
        version_number=2,
        status=DocumentStatus.DRAFT,
        effective_date=date(2026, 1, 1),
        change_description="Изменение",
        change_justification="Обоснование",
        creator=creator,
        scan_file_id=selected_scan_id,
        scan_file=SimpleNamespace(original_name="selected.pdf"),
        editable_file_id=selected_editable_id,
        editable_file=SimpleNamespace(original_name="selected.docx"),
    )
    instruction = SimpleNamespace(urza_id=uuid7())

    html = templates.get_template("objects/urza_instruction.html").render(
        instruction=instruction,
        versions=[current_version, selected_version],
        selected_version=selected_version,
        current_version=current_version,
        actions=set(),
        history_open=False,
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
    file_id = uuid7()
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
