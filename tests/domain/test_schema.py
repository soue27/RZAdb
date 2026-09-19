from datetime import date

from app.domain.schema import SchemaForm, SchemaRecord


def test_schema_form_model() -> None:
    form = SchemaForm()

    assert form.urza_id is None


def test_schema_record_model() -> None:
    record = SchemaRecord(
        schema_number="Э3",
        schema_name="Исполнительная схема РЗА",
        change_description="Изменена схема подключения защиты",
        change_justification="Модернизация устройства РЗА",
        upload_date=date(2026, 9, 13),
    )

    assert record.schema_number == "Э3"
    assert record.schema_name == "Исполнительная схема РЗА"
    assert record.change_description == "Изменена схема подключения защиты"
    assert record.change_justification == "Модернизация устройства РЗА"
    assert record.upload_date == date(2026, 9, 13)

    assert record.schema_form_id is None
    assert record.created_by is None
    assert record.scan_file_id is None
    assert record.editable_file_id is None
    assert record.signed_form_file_id is None
    assert record.task_id is None