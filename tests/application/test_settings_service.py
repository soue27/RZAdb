from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.settings.service import SettingsService
from app.domain.settings_record import SettingsRecord
from app.domain.rza_settings import SettingsForm


@pytest.mark.asyncio
async def test_get_by_urza_returns_form_when_access_allowed(system_user_id) -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    settings_form = SettingsForm(
        id=uuid7(),
        urza_id=urza_id,
        created_by=system_user_id,
        updated_by=system_user_id,
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
    assert result.created_by == user_id
    assert result.updated_by == user_id

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
async def test_create_form_raises_when_form_already_exists(system_user_id) -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    existing_form = SettingsForm(
        id=uuid7(),
        urza_id=urza_id,
        created_by=system_user_id,
        updated_by=system_user_id,
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
async def test_create_record_success(system_user_id) -> None:
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
        created_by=system_user_id,
        updated_by=system_user_id,
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
    assert result.updated_by == user_id
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
async def test_create_record_creates_form_when_form_not_exists() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    signed_form_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = None

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    record = await service.create_record(
        user_id=user_id,
        urza_id=urza_id,
        change_date=date(2026, 9, 17),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        signed_form_file_id=signed_form_file_id,
    )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )

    repository.add_form.assert_awaited_once()

    created_form = repository.add_form.await_args.args[0]

    assert isinstance(created_form, SettingsForm)
    assert created_form.urza_id == urza_id
    assert created_form.created_by == user_id
    assert created_form.updated_by == user_id

    repository.add_record.assert_awaited_once_with(record)

    assert record.settings_form_id == created_form.id
    assert record.created_by == user_id
    assert record.updated_by == user_id
    assert record.signed_form_file_id == signed_form_file_id


@pytest.mark.asyncio
async def test_delete_record_raises_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        PermissionError,
        match="Доступ к URZA запрещён",
    ):
        await service.delete_record(
            user_id=user_id,
            urza_id=urza_id,
            record_id=record_id,
        )

    repository.get_record_by_id.assert_not_awaited()
    repository.get_form_by_urza_id.assert_not_awaited()
    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_record_raises_when_record_not_exists() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_record_by_id.return_value = None

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Запись уставок не найдена",
    ):
        await service.delete_record(
            user_id=user_id,
            urza_id=urza_id,
            record_id=record_id,
        )

    repository.get_record_by_id.assert_awaited_once_with(
        record_id,
    )
    repository.get_form_by_urza_id.assert_not_awaited()
    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_record_raises_when_record_belongs_to_another_urza(
    system_user_id,
) -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    another_urza_id = uuid7()
    record_id = uuid7()
    settings_form_id = uuid7()

    settings_form = SettingsForm(
        id=settings_form_id,
        urza_id=urza_id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    record = SettingsRecord(
        id=record_id,
        settings_form_id=uuid7(),
        change_date=date(2026, 9, 17),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        signed_form_file_id=uuid7(),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_record_by_id.return_value = record
    repository.get_form_by_urza_id.return_value = settings_form

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Запись уставок не принадлежит данному URZA",
    ):
        await service.delete_record(
            user_id=user_id,
            urza_id=urza_id,
            record_id=record_id,
        )

    repository.get_record_by_id.assert_awaited_once_with(
        record_id,
    )
    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )
    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_record_success(system_user_id) -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()
    settings_form_id = uuid7()

    settings_form = SettingsForm(
        id=settings_form_id,
        urza_id=urza_id,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    record = SettingsRecord(
        id=record_id,
        settings_form_id=settings_form_id,
        change_date=date(2026, 9, 17),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        signed_form_file_id=uuid7(),
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_record_by_id.return_value = record
    repository.get_form_by_urza_id.return_value = settings_form

    service = SettingsService(
        repository=repository,
        access_service=access_service,
    )

    before = datetime.now(timezone.utc)

    await service.delete_record(
        user_id=user_id,
        urza_id=urza_id,
        record_id=record_id,
    )

    after = datetime.now(timezone.utc)

    assert record.deleted_at is not None
    assert before <= record.deleted_at <= after
    assert record.deleted_by == user_id
    assert record.updated_by == user_id

    repository.get_record_by_id.assert_awaited_once_with(
        record_id,
    )
    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )
    repository.flush.assert_awaited_once()
