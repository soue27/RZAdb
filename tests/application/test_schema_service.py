from datetime import date
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.schema.service import SchemaService
from app.domain.schema import SchemaForm


@pytest.mark.asyncio
async def test_get_by_urza_returns_form_when_access_allowed() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    schema_form = SchemaForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = schema_form

    service = SchemaService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_by_urza(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is schema_form

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

    service = SchemaService(
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

    service = SchemaService(
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

    service = SchemaService(
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

    existing_form = SchemaForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = existing_form

    service = SchemaService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Форма схем для данного URZA уже существует",
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
    schema_form_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()
    signed_form_file_id = uuid7()
    task_id = uuid7()

    schema_form = SchemaForm(
        id=schema_form_id,
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_form_by_urza_id.return_value = schema_form

    service = SchemaService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.create_record(
        user_id=user_id,
        urza_id=urza_id,
        schema_number="СХ-110-01",
        schema_name="Исполнительная схема РЗА",
        change_description="Изменена цепь отключения",
        change_justification="Изменение схемы подключения",
        upload_date=date(2026, 9, 17),
        signed_form_file_id=signed_form_file_id,
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        task_id=task_id,
    )

    assert result.schema_form_id == schema_form_id
    assert result.schema_number == "СХ-110-01"
    assert result.schema_name == "Исполнительная схема РЗА"
    assert result.change_description == "Изменена цепь отключения"
    assert result.change_justification == "Изменение схемы подключения"
    assert result.upload_date == date(2026, 9, 17)
    assert result.created_by == user_id
    assert result.scan_file_id == scan_file_id
    assert result.editable_file_id == editable_file_id
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

    service = SchemaService(
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
            schema_number="СХ-110-01",
            schema_name="Исполнительная схема РЗА",
            change_description="Изменена цепь отключения",
            change_justification="Изменение схемы подключения",
            upload_date=date(2026, 9, 17),
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

    service = SchemaService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="Форма схем для данного URZA не существует",
    ):
        await service.create_record(
            user_id=user_id,
            urza_id=urza_id,
            schema_number="СХ-110-01",
            schema_name="Исполнительная схема РЗА",
            change_description="Изменена цепь отключения",
            change_justification="Изменение схемы подключения",
            upload_date=date(2026, 9, 17),
            signed_form_file_id=uuid7(),
        )

    repository.get_form_by_urza_id.assert_awaited_once_with(
        urza_id,
    )
    repository.add_record.assert_not_awaited()
