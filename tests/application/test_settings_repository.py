from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.settings.repository import SettingsRepository
from app.domain.enums import DocumentStatus
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


def make_record(user_id, form_id=None, status=DocumentStatus.DRAFT):
    return SettingsRecord(
        id=uuid7(),
        settings_form_id=form_id or uuid7(),
        change_date=date.today(),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        status=status,
        created_by=user_id,
        updated_by=user_id,
        signed_form_file_id=uuid7(),
    )


@pytest.mark.asyncio
async def test_get_form_by_id_filters_soft_deleted():
    session = AsyncMock()
    settings_form = SettingsForm(id=uuid7(), urza_id=uuid7(), created_by=uuid7(), updated_by=uuid7())
    session.scalar.return_value = settings_form
    repository = SettingsRepository(session)

    assert await repository.get_form_by_id(settings_form.id) is settings_form
    sql = str(session.scalar.await_args.args[0])
    assert "settings_forms.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_form_by_urza_id_filters_soft_deleted():
    session = AsyncMock()
    urza_id = uuid7()
    settings_form = SettingsForm(id=uuid7(), urza_id=urza_id, created_by=uuid7(), updated_by=uuid7())
    session.scalar.return_value = settings_form
    repository = SettingsRepository(session)

    assert await repository.get_form_by_urza_id(urza_id) is settings_form
    sql = str(session.scalar.await_args.args[0])
    assert "settings_forms.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_record_by_id_filters_soft_deleted():
    session = AsyncMock()
    record = make_record(uuid7())
    session.scalar.return_value = record
    repository = SettingsRepository(session)

    assert await repository.get_record_by_id(record.id) is record
    sql = str(session.scalar.await_args.args[0])
    assert "settings_records.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_records_returns_active_sorted_records():
    session = AsyncMock()
    records = [make_record(uuid7())]
    scalar_result = MagicMock()
    scalar_result.all.return_value = records
    session.scalars.return_value = scalar_result
    repository = SettingsRepository(session)

    assert await repository.get_records(records[0].settings_form_id) == records
    sql = str(session.scalars.await_args.args[0])
    assert "settings_records.deleted_at IS NULL" in sql
    assert "settings_records.change_date DESC" in sql
    assert "settings_records.created_at DESC" in sql
    assert "settings_records.id DESC" in sql


@pytest.mark.asyncio
async def test_get_current_approved_filters_and_limits():
    session = AsyncMock()
    form_id = uuid7()
    record = make_record(uuid7(), form_id, DocumentStatus.APPROVED)
    session.scalar.return_value = record
    repository = SettingsRepository(session)

    assert await repository.get_current_approved(form_id) is record
    sql = str(session.scalar.await_args.args[0])
    assert "settings_records.deleted_at IS NULL" in sql
    assert "settings_records.status =" in sql
    assert "settings_records.change_date DESC" in sql
    assert "settings_records.created_at DESC" in sql
    assert "settings_records.id DESC" in sql
    assert "LIMIT" in sql


@pytest.mark.asyncio
async def test_get_unfinished_filters_to_active_draft_and_under_review():
    session = AsyncMock()
    record = make_record(uuid7(), status=DocumentStatus.UNDER_REVIEW)
    session.scalar.return_value = record
    repository = SettingsRepository(session)

    assert await repository.get_unfinished(record.settings_form_id) is record
    sql = str(session.scalar.await_args.args[0])
    assert "settings_records.deleted_at IS NULL" in sql
    assert "settings_records.status IN" in sql
    assert "LIMIT" in sql


@pytest.mark.asyncio
async def test_add_form_flushes_without_commit():
    session = MagicMock()
    session.flush = AsyncMock()
    settings_form = SettingsForm(id=uuid7(), urza_id=uuid7(), created_by=uuid7(), updated_by=uuid7())
    repository = SettingsRepository(session)

    assert await repository.add_form(settings_form) is settings_form
    session.add.assert_called_once_with(settings_form)
    session.flush.assert_awaited_once()
    assert not hasattr(session, "commit") or not session.commit.called


@pytest.mark.asyncio
async def test_add_record_flushes_without_commit():
    session = MagicMock()
    session.flush = AsyncMock()
    record = make_record(uuid7())
    repository = SettingsRepository(session)

    assert await repository.add_record(record) is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()
    assert not hasattr(session, "commit") or not session.commit.called


@pytest.mark.asyncio
async def test_save_and_flush():
    session = MagicMock()
    session.flush = AsyncMock()
    repository = SettingsRepository(session)
    record = make_record(uuid7())

    assert await repository.save(record) is record
    await repository.flush()
    assert session.flush.await_count == 2
