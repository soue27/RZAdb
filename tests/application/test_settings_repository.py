from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.settings.repository import SettingsRepository
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


@pytest.mark.asyncio
async def test_get_form_by_id_returns_settings_form() -> None:
    session = AsyncMock()

    settings_form = SettingsForm(
        id=uuid7(),
        urza_id=uuid7(),
    )

    session.get.return_value = settings_form

    repository = SettingsRepository(session)

    result = await repository.get_form_by_id(settings_form.id)

    assert result is settings_form
    session.get.assert_awaited_once_with(
        SettingsForm,
        settings_form.id,
    )


@pytest.mark.asyncio
async def test_get_form_by_urza_id_returns_settings_form() -> None:
    session = AsyncMock()

    urza_id = uuid7()

    settings_form = SettingsForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    session.scalar.return_value = settings_form

    repository = SettingsRepository(session)

    result = await repository.get_form_by_urza_id(urza_id)

    assert result is settings_form
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_record_by_id_returns_settings_record() -> None:
    session = AsyncMock()

    record_id = uuid7()

    settings_record = SettingsRecord(
        id=record_id,
        settings_form_id=uuid7(),
        change_date=date.today(),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        created_by=uuid7(),
        signed_form_file_id=uuid7(),
    )

    session.get.return_value = settings_record

    repository = SettingsRepository(session)

    result = await repository.get_record_by_id(record_id)

    assert result is settings_record
    session.get.assert_awaited_once_with(
        SettingsRecord,
        record_id,
    )


@pytest.mark.asyncio
async def test_add_form() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    settings_form = SettingsForm(
        id=uuid7(),
        urza_id=uuid7(),
    )

    repository = SettingsRepository(session)

    result = await repository.add_form(settings_form)

    assert result is settings_form
    session.add.assert_called_once_with(settings_form)
    session.flush.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_record() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    record = SettingsRecord(
        id=uuid7(),
        settings_form_id=uuid7(),
        change_date=date.today(),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        created_by=uuid7(),
        signed_form_file_id=uuid7(),
    )

    repository = SettingsRepository(session)

    result = await repository.add_record(record)

    assert result is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()