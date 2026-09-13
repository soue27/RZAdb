from datetime import date, datetime, timezone

from app.domain.settings_record import SettingsRecord


def test_settings_record_model() -> None:
    created_at = datetime.now(timezone.utc)

    record = SettingsRecord(
        change_date=date(2026, 9, 13),
        parameter_name="Ток срабатывания",
        initial_setting="5.0 А",
        new_setting="5.5 А",
        change_reason="Изменение уставки защиты",
        created_at=created_at,
    )
    assert record.change_date == date(2026, 9, 13)
    assert record.parameter_name == "Ток срабатывания"
    assert record.initial_setting == "5.0 А"
    assert record.new_setting == "5.5 А"
    assert record.change_reason == "Изменение уставки защиты"
    assert record.created_at == created_at

    assert record.settings_form_id is None
    assert record.created_by is None
    assert record.signed_form_file_id is None
    assert record.task_id is None