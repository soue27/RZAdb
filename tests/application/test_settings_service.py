from unittest.mock import AsyncMock, MagicMock
from datetime import date

import pytest
from uuid6 import uuid7

from app.application.settings.repository import SettingsRepository
from app.application.settings.service import SettingsService
from app.domain.rza_settings import SettingsForm


@pytest.mark.asyncio
async def test_get_by_urza_returns_form_when_access_allowed() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    settings_form = SettingsForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = settings_form

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_by_urza(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is settings_form

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )

@pytest.mark.asyncio
async def test_get_by_urza_returns_none_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_by_urza(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is None

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_form_by_urza_id.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_form_success() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = None

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.create_form(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result.urza_id == urza_id

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )

    repository.add_form.assert_awaited_once_with(result)

@pytest.mark.asyncio
async def test_create_form_raises_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        PermissionError,
        match="Доступ к URZA запрещён",
    ):
        await service.create_form(
            user_id=user_id,
            urza_id=urza_id,
        )

    repository.get_form_by_urza_id.assert_not_awaited()
    repository.add_form.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_form_raises_when_form_already_exists() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    existing_form = SettingsForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = existing_form

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Форма уставок для данного URZA уже существует",
    ):
        await service.create_form(
            user_id=user_id,
            urza_id=urza_id,
        )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )
    repository.add_form.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_record_success() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    settings_form_id = uuid7()
    signed_form_file_id = uuid7()
    task_id = uuid7()

    settings_form = SettingsForm(
        id=settings_form_id,
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = settings_form

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.create_record(
        user_id=user_id,
        urza_id=urza_id,
        change_date=date(2026, 9, 17),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        signed_form_file_id=signed_form_file_id,
        task_id=task_id,
    )

    assert result.settings_form_id == settings_form_id
    assert result.change_date == date(2026, 9, 17)
    assert result.parameter_name == "Ток срабатывания"
    assert result.initial_setting == "1.0 A"
    assert result.new_setting == "1.2 A"
    assert result.change_reason == "Корректировка уставки"
    assert result.created_by == user_id
    assert result.signed_form_file_id == signed_form_file_id
    assert result.task_id == task_id

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )

    repository.add_record.assert_awaited_once_with(result)

@pytest.mark.asyncio
async def test_create_record_raises_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        PermissionError,
        match="Доступ к URZA запрещён",
    ):
        await service.create_record(
            user_id=user_id,
            urza_id=urza_id,
            change_date=date(2026, 9, 17),
            parameter_name="Ток срабатывания",
            initial_setting="1.0 A",
            new_setting="1.2 A",
            change_reason="Корректировка уставки",
            signed_form_file_id=uuid7(),
        )

    repository.get_form_by_urza_id.assert_not_awaited()
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_record_raises_when_form_not_exists() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = None

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Форма уставок для данного URZA не существует",
    ):
        await service.create_record(
            user_id=user_id,
            urza_id=urza_id,
            change_date=date(2026, 9, 17),
            parameter_name="Ток срабатывания",
            initial_setting="1.0 A",
            new_setting="1.2 A",
            change_reason="Корректировка уставки",
            signed_form_file_id=uuid7(),
        )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )
    repository.add_record.assert_not_awaited()
