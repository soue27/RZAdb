from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.schema.repository import SchemaRepository
from app.domain.enums import DocumentStatus
from app.domain.schema import SchemaForm, SchemaRecord


def _sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_get_form_by_id_filters_soft_deleted() -> None:
    session = AsyncMock()
    form_id = uuid7()
    form = MagicMock(spec=SchemaForm)
    session.scalar.return_value = form

    repository = SchemaRepository(session)

    assert await repository.get_form_by_id(form_id) is form
    sql = _sql(session.scalar.await_args.args[0])
    assert "schema_forms.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_form_by_urza_id_filters_soft_deleted() -> None:
    session = AsyncMock()
    urza_id = uuid7()
    form = MagicMock(spec=SchemaForm)
    session.scalar.return_value = form

    repository = SchemaRepository(session)

    assert await repository.get_form_by_urza_id(urza_id) is form
    sql = _sql(session.scalar.await_args.args[0])
    assert "schema_forms.urza_id" in sql
    assert "schema_forms.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_by_id_filters_soft_deleted_record() -> None:
    session = AsyncMock()
    record_id = uuid7()
    record = MagicMock(spec=SchemaRecord)
    session.scalar.return_value = record

    repository = SchemaRepository(session)

    assert await repository.get_by_id(record_id) is record
    sql = _sql(session.scalar.await_args.args[0])
    assert "schema_records.id" in sql
    assert "schema_records.deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_record_by_id_uses_active_query_alias() -> None:
    session = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    session.scalar.return_value = record

    repository = SchemaRepository(session)

    assert await repository.get_record_by_id(uuid7()) is record
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_active_filters_deleted_and_orders_deterministically() -> None:
    session = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    scalar_result = MagicMock()
    scalar_result.all.return_value = [record]
    session.scalars.return_value = scalar_result
    repository = SchemaRepository(session)

    assert await repository.list_active(uuid7()) == [record]
    sql = _sql(session.scalars.await_args.args[0])
    assert "schema_records.deleted_at IS NULL" in sql
    assert "ORDER BY schema_records.upload_date DESC" in sql
    assert "schema_records.created_at DESC" in sql
    assert "schema_records.id DESC" in sql


@pytest.mark.asyncio
async def test_get_by_form_and_existing_list_method_delegate_to_active_list() -> None:
    session = AsyncMock()
    repository = SchemaRepository(session)
    repository.list_active = AsyncMock(return_value=[])
    form_id = uuid7()

    assert await repository.get_by_form(form_id) == []
    assert await repository.get_records_by_form_id(form_id) == []
    assert repository.list_active.await_args_list[0].args == (form_id,)
    assert repository.list_active.await_args_list[1].args == (form_id,)


@pytest.mark.asyncio
async def test_get_current_approved_filters_status_delete_and_limits_one() -> None:
    session = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    session.scalar.return_value = record
    repository = SchemaRepository(session)

    assert await repository.get_current_approved(uuid7()) is record
    sql = _sql(session.scalar.await_args.args[0])
    assert "schema_records.deleted_at IS NULL" in sql
    assert "schema_records.status = 'approved'" in sql
    assert "ORDER BY schema_records.upload_date DESC" in sql
    assert "schema_records.created_at DESC" in sql
    assert "schema_records.id DESC" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_get_unfinished_filters_deleted_and_only_unfinished_statuses() -> None:
    session = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    session.scalar.return_value = record
    repository = SchemaRepository(session)

    assert await repository.get_unfinished(uuid7()) is record
    sql = _sql(session.scalar.await_args.args[0])
    assert "schema_records.deleted_at IS NULL" in sql
    assert "schema_records.status IN ('draft', 'under_review')" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_add_form_adds_and_flushes() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    form = MagicMock(spec=SchemaForm)
    repository = SchemaRepository(session)

    assert await repository.add_form(form) is form
    session.add.assert_called_once_with(form)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_record_adds_and_flushes() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    repository = SchemaRepository(session)

    assert await repository.add_record(record) is record
    session.add.assert_called_once_with(record)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_only_flushes_without_commit() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    repository = SchemaRepository(session)

    assert await repository.save(record) is record
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_soft_delete_sets_audit_fields_and_flushes(system_user_id) -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    record = MagicMock(spec=SchemaRecord)
    repository = SchemaRepository(session)

    result = await repository.soft_delete(record, system_user_id)

    assert result is record
    assert record.deleted_at.tzinfo is not None
    assert record.deleted_by == system_user_id
    assert record.updated_at == record.deleted_at
    assert record.updated_by == system_user_id
    session.flush.assert_awaited_once()
    session.delete.assert_not_called()
