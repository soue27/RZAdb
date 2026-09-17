from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.schema.repository import SchemaRepository
from app.domain.schema import SchemaForm, SchemaRecord


@pytest.mark.asyncio
async def test_get_form_by_id_returns_schema_form() -> None:
    session = AsyncMock()

    schema_form = SchemaForm(
        id=uuid7(),
        urza_id=uuid7(),
    )

    session.get.return_value = schema_form

    repository = SchemaRepository(session)

    result = await repository.get_form_by_id(schema_form.id)

    assert result is schema_form
    session.get.assert_awaited_once_with(
        SchemaForm,
        schema_form.id,
    )


@pytest.mark.asyncio
async def test_get_form_by_urza_id_returns_schema_form() -> None:
    session = AsyncMock()

    urza_id = uuid7()

    schema_form = SchemaForm(
        id=uuid7(),
        urza_id=urza_id,
    )

    session.scalar.return_value = schema_form

    repository = SchemaRepository(session)

    result = await repository.get_form_by_urza_id(urza_id)

    assert result is schema_form
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_record_by_id_returns_schema_record() -> None:
    session = AsyncMock()

    record_id = uuid7()
    schema_record = MagicMock(spec=SchemaRecord)

    session.get.return_value = schema_record

    repository = SchemaRepository(session)

    result = await repository.get_record_by_id(record_id)

    assert result is schema_record
    session.get.assert_awaited_once_with(
        SchemaRecord,
        record_id,
    )

@pytest.mark.asyncio
async def test_add_form() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    schema_form = SchemaForm(
        id=uuid7(),
        urza_id=uuid7(),
    )

    repository = SchemaRepository(session)

    result = await repository.add_form(schema_form)

    assert result is schema_form
    session.add.assert_called_once_with(schema_form)
    session.flush.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_record() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    record = MagicMock(spec=SchemaRecord)

    repository = SchemaRepository(session)

    result = await repository.add_record(record)

    assert result is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()