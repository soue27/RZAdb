from datetime import UTC, date, datetime

from uuid6 import uuid7

from app.domain.enums import DocumentStatus
from app.domain.settings_record import SettingsRecord


def test_settings_record_model(system_user_id) -> None:
    created_at = datetime.now(UTC)

    record = SettingsRecord(
        change_date=date(2026, 9, 13),
        parameter_name="Ток срабатывания",
        initial_setting="5.0 А",
        new_setting="5.5 А",
        change_reason="Изменение уставки защиты",
        status=DocumentStatus.DRAFT,
        signed_form_file_id=uuid7(),
        created_at=created_at,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    assert record.change_date == date(2026, 9, 13)
    assert record.parameter_name == "Ток срабатывания"
    assert record.initial_setting == "5.0 А"
    assert record.new_setting == "5.5 А"
    assert record.change_reason == "Изменение уставки защиты"
    assert record.status is DocumentStatus.DRAFT
    assert record.created_at == created_at

    assert record.settings_form_id is None
    assert record.created_by == system_user_id
    assert record.signed_form_file_id is not None
    assert SettingsRecord.__table__.c.status.nullable is False
    assert SettingsRecord.__table__.c.signed_form_file_id.nullable is False
    assert SettingsRecord.__table__.c.status.type.name == "document_status"
    assert record.task_id is None
