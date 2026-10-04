from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from uuid6 import uuid7

from app.application.schema.service import SchemaService
from app.domain.enums import DocumentStatus, TaskStatus, TaskWorkType, UserRole
from app.domain.schema import SchemaForm, SchemaRecord


def _service(role: UserRole, *, accessible: bool = True):
    repository = AsyncMock()
    user_id = uuid7()
    urza_id = uuid7()
    user = SimpleNamespace(role=role, active=True, deleted_at=None)
    user_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    access_service = SimpleNamespace(
        can_access_urza=AsyncMock(return_value=accessible),
        user_repository=user_repository,
    )
    task_repository = AsyncMock()
    service = SchemaService(repository, access_service, task_repository)
    return service, repository, access_service, user_id, urza_id


def _form(user_id, urza_id):
    return SchemaForm(
        id=uuid7(),
        urza_id=urza_id,
        created_by=user_id,
        updated_by=user_id,
    )


def _record(user_id, form_id, status, **values):
    return SchemaRecord(
        id=values.pop("id", uuid7()),
        schema_form_id=form_id,
        schema_number="SC-1",
        schema_name="Schema",
        change_description="Change",
        change_justification="Reason",
        upload_date=date(2026, 1, 1),
        status=status,
        signed_form_file_id=values.pop("signed_form_file_id", uuid7()),
        created_by=user_id,
        updated_by=user_id,
        **values,
    )


async def _return_argument(record):
    return record


async def _persist_form(form):
    form.id = form.id or uuid7()
    return form


def _task(task_id, user_id, default_urza_id, **overrides):
    values = {
        "id": task_id,
        "urza_id": default_urza_id,
        "work_type": TaskWorkType.SCHEMES,
        "assigned_to": user_id,
        "status": TaskStatus.IN_PROGRESS,
        "deleted_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_get_by_urza_returns_form_when_access_allowed() -> None:
    service, repository, access_service, user_id, urza_id = _service(
        UserRole.ENGINEER
    )
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_urza_id.return_value = schema_form

    result = await service.get_by_urza(user_id, urza_id)

    assert result is schema_form
    access_service.can_access_urza.assert_awaited_once_with(user_id, urza_id)
    repository.get_form_by_urza_id.assert_awaited_once_with(urza_id)


@pytest.mark.asyncio
async def test_get_by_urza_returns_none_when_access_denied() -> None:
    service, repository, _, user_id, urza_id = _service(
        UserRole.ENGINEER, accessible=False
    )

    assert await service.get_by_urza(user_id, urza_id) is None
    repository.get_form_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_details_returns_active_records_for_accessible_urza() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    records = [_record(user_id, schema_form.id, DocumentStatus.APPROVED)]
    repository.get_form_by_urza_id.return_value = schema_form
    repository.list_active.return_value = records

    assert await service.get_details(user_id, urza_id) == (schema_form, records)
    repository.list_active.assert_awaited_once_with(schema_form.id)


@pytest.mark.asyncio
async def test_get_details_returns_empty_when_access_denied() -> None:
    service, repository, _, user_id, urza_id = _service(
        UserRole.ENGINEER, accessible=False
    )

    assert await service.get_details(user_id, urza_id) == (None, [])
    repository.get_form_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_form_success() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    repository.get_form_by_urza_id.return_value = None
    repository.add_form.side_effect = _persist_form

    result = await service.create_form(user_id, urza_id)

    assert result.urza_id == urza_id
    assert result.created_by == user_id
    repository.add_form.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_form_rejects_existing_form() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    repository.get_form_by_urza_id.return_value = _form(user_id, urza_id)

    with pytest.raises(ValueError, match="уже существует"):
        await service.create_form(user_id, urza_id)
    repository.add_form.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (UserRole.ENGINEER, DocumentStatus.DRAFT),
        (UserRole.ADMIN, DocumentStatus.DRAFT),
        (UserRole.SUPERADMIN, DocumentStatus.DRAFT),
        (UserRole.MANAGER, DocumentStatus.APPROVED),
    ],
)
async def test_create_sets_initial_status(role, expected_status) -> None:
    service, repository, _, user_id, urza_id = _service(role)
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_urza_id.return_value = schema_form
    repository.get_unfinished.return_value = None
    repository.add_record.side_effect = _return_argument
    task_id = uuid7()
    service.task_repository.get_by_id.return_value = _task(
        task_id, user_id, urza_id
    )
    service.task_repository.get_schema_record_by_task_id.return_value = None

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        schema_number="SC-1",
        schema_name="Schema",
        change_description="Change",
        change_justification="Reason",
        upload_date=date(2026, 1, 2),
        signed_form_file_id=uuid7(),
        task_id=task_id,
        scan_file_id=uuid7(),
    )

    assert result.status is expected_status
    assert result.task_id is not None
    assert result.scan_file_id is not None
    repository.add_record.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_creates_form_if_missing() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    repository.get_form_by_urza_id.return_value = None
    repository.add_form.side_effect = _persist_form
    repository.get_unfinished.return_value = None
    repository.add_record.side_effect = _return_argument

    result = await service.create(
        user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
        date(2026, 1, 2), uuid7(),
    )

    assert result.schema_form_id is not None
    repository.add_form.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_missing_signed_form() -> None:
    service, _, _, user_id, urza_id = _service(UserRole.ENGINEER)

    with pytest.raises(ValueError, match="Подписанный формуляр"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), None,
        )


@pytest.mark.asyncio
async def test_create_rejects_when_access_denied() -> None:
    service, repository, _, user_id, urza_id = _service(
        UserRole.ENGINEER, accessible=False
    )

    with pytest.raises(PermissionError, match="Доступ к URZA"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(),
        )
    repository.get_form_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_existing_unfinished_record() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_urza_id.return_value = schema_form
    repository.get_unfinished.return_value = _record(
        user_id, schema_form.id, DocumentStatus.DRAFT
    )

    with pytest.raises(ValueError, match="незавершённая запись схем"):
        await service.create(
            user_id, urza_id, "SC-2", "New", "Change", "Reason",
            date(2026, 1, 2), uuid7(),
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_translates_partial_unique_index_integrity_error() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_urza_id.return_value = schema_form
    repository.get_unfinished.return_value = None
    original_error = Exception(
        "duplicate key violates uq_schema_records_one_active_unfinished_per_form"
    )
    repository.add_record.side_effect = IntegrityError(
        "INSERT", {}, original_error
    )

    with pytest.raises(ValueError, match="незавершённая запись схем"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(),
        )


@pytest.mark.asyncio
async def test_task_create_keeps_existing_file_validation_contract() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_urza_id.return_value = schema_form
    repository.get_unfinished.return_value = None
    repository.add_record.side_effect = _return_argument
    first_task_id, second_task_id = uuid7(), uuid7()
    service.task_repository.get_by_id.side_effect = [
        _task(first_task_id, user_id, urza_id),
        _task(second_task_id, user_id, urza_id),
    ]
    service.task_repository.get_schema_record_by_task_id.return_value = None

    with pytest.raises(ValueError, match="скан или редактируемый файл"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(), task_id=first_task_id,
        )

    result = await service.create(
        user_id, urza_id, "SC-2", "Schema", "Change", "Reason",
        date(2026, 1, 2), uuid7(), task_id=second_task_id,
        editable_file_id=uuid7(),
    )
    assert result.editable_file_id is not None


@pytest.mark.asyncio
async def test_create_accepts_valid_task_result() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    task_id = uuid7()
    repository.get_form_by_urza_id.return_value = schema_form
    repository.get_unfinished.return_value = None
    repository.add_record.side_effect = _return_argument
    service.task_repository.get_by_id.return_value = _task(
        task_id, user_id, urza_id
    )
    service.task_repository.get_schema_record_by_task_id.return_value = None

    record = await service.create(
        user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
        date(2026, 1, 2), uuid7(), scan_file_id=uuid7(), task_id=task_id,
    )

    assert record.task_id == task_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"work_type": TaskWorkType.PROGRAM}, ValueError, "не предназначена"),
        ({"urza_id": uuid7()}, ValueError, "другой URZA"),
        ({"assigned_to": uuid7()}, PermissionError, "назначенный исполнитель"),
        ({"assigned_to": None}, PermissionError, "назначенный исполнитель"),
        ({"status": TaskStatus.ASSIGNED}, ValueError, "только по задаче в работе"),
        ({"status": TaskStatus.COMPLETED}, ValueError, "только по задаче в работе"),
        ({"deleted_at": datetime.now(timezone.utc)}, ValueError, "не найдена"),
    ],
)
async def test_create_rejects_ineligible_task(overrides, error, message) -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    task_id = uuid7()
    service.task_repository.get_by_id.return_value = _task(
        task_id, user_id, urza_id, **overrides
    )

    with pytest.raises(error, match=message):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(), scan_file_id=uuid7(), task_id=task_id,
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_missing_task() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    service.task_repository.get_by_id.return_value = None

    with pytest.raises(ValueError, match="Активная задача не найдена"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(), scan_file_id=uuid7(), task_id=uuid7(),
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_existing_task_result() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    task_id = uuid7()
    service.task_repository.get_by_id.return_value = _task(
        task_id, user_id, urza_id
    )
    service.task_repository.get_schema_record_by_task_id.return_value = object()

    with pytest.raises(ValueError, match="уже существует активный результат"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(), scan_file_id=uuid7(), task_id=task_id,
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_translates_task_unique_index_integrity_error() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    task_id = uuid7()
    repository.get_form_by_urza_id.return_value = _form(user_id, urza_id)
    repository.get_unfinished.return_value = None
    service.task_repository.get_by_id.return_value = _task(
        task_id, user_id, urza_id
    )
    service.task_repository.get_schema_record_by_task_id.return_value = None
    original_error = Exception(
        "duplicate key violates uq_schema_records_one_active_per_task"
    )
    repository.add_record.side_effect = IntegrityError("INSERT", {}, original_error)

    with pytest.raises(ValueError, match="уже существует активный результат"):
        await service.create(
            user_id, urza_id, "SC-1", "Schema", "Change", "Reason",
            date(2026, 1, 2), uuid7(), scan_file_id=uuid7(), task_id=task_id,
        )


@pytest.mark.asyncio
async def test_update_changes_only_draft_and_keeps_status() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.DRAFT)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form
    repository.save.side_effect = _return_argument

    result = await service.update(
        user_id, urza_id, record.id, "SC-2", "Updated", "New change",
        "Reason", date(2026, 2, 1), scan_file_id=uuid7(),
    )

    assert result.schema_number == "SC-2"
    assert result.schema_name == "Updated"
    assert result.status is DocumentStatus.DRAFT
    assert result.signed_form_file_id is not None
    repository.save.assert_awaited_once_with(record)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DocumentStatus.APPROVED, DocumentStatus.UNDER_REVIEW])
async def test_update_rejects_non_draft(status) -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, status)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(ValueError, match="только черновик"):
        await service.update(
            user_id, urza_id, record.id, "SC-2", "Updated", "Change",
            "Reason", date(2026, 2, 1),
        )
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_moves_draft_to_under_review() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.DRAFT)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form
    repository.save.side_effect = _return_argument

    result = await service.submit_for_review(user_id, urza_id, record.id)

    assert result.status is DocumentStatus.UNDER_REVIEW
    repository.save.assert_awaited_once_with(record)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED]
)
async def test_submit_rejects_non_draft(status) -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, status)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(ValueError, match="только черновик"):
        await service.submit_for_review(user_id, urza_id, record.id)
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_by_accessible_manager() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.UNDER_REVIEW)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form
    repository.save.side_effect = _return_argument

    result = await service.approve(user_id, urza_id, record.id)

    assert result.status is DocumentStatus.APPROVED


@pytest.mark.asyncio
async def test_approve_rejects_non_manager() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ENGINEER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.UNDER_REVIEW)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(PermissionError, match="только MANAGER"):
        await service.approve(user_id, urza_id, record.id)
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_rejects_manager_without_urza_access() -> None:
    service, repository, _, user_id, urza_id = _service(
        UserRole.MANAGER, accessible=False
    )
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.UNDER_REVIEW)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(PermissionError, match="Доступ к URZA"):
        await service.approve(user_id, urza_id, record.id)
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DocumentStatus.DRAFT, DocumentStatus.APPROVED])
async def test_approve_rejects_wrong_status(status) -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, status)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(ValueError, match="только схему на согласовании"):
        await service.approve(user_id, urza_id, record.id)


@pytest.mark.asyncio
async def test_return_to_draft_by_reviewer() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.UNDER_REVIEW)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form
    repository.save.side_effect = _return_argument

    result = await service.return_to_draft(user_id, urza_id, record.id)

    assert result.status is DocumentStatus.DRAFT


@pytest.mark.asyncio
async def test_return_rejects_non_reviewer() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ADMIN)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.UNDER_REVIEW)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(PermissionError, match="только MANAGER"):
        await service.return_to_draft(user_id, urza_id, record.id)


@pytest.mark.asyncio
async def test_return_rejects_wrong_status() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.MANAGER)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.DRAFT)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(ValueError, match="только схему на согласовании"):
        await service.return_to_draft(user_id, urza_id, record.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN])
async def test_delete_soft_deletes_for_admin_roles(role) -> None:
    service, repository, _, user_id, urza_id = _service(role)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.APPROVED)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form
    repository.soft_delete.return_value = record

    result = await service.delete(user_id, urza_id, record.id)

    assert result.status is DocumentStatus.APPROVED
    repository.soft_delete.assert_awaited_once_with(record, user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
async def test_delete_rejects_engineer_and_manager(role) -> None:
    service, repository, _, user_id, urza_id = _service(role)
    schema_form = _form(user_id, urza_id)
    record = _record(user_id, schema_form.id, DocumentStatus.APPROVED)
    repository.get_by_id.return_value = record
    repository.get_form_by_id.return_value = schema_form

    with pytest.raises(PermissionError, match="только ADMIN или SUPERADMIN"):
        await service.delete(user_id, urza_id, record.id)
    repository.soft_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_available_actions_for_draft_and_approved() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ADMIN)
    schema_form = _form(user_id, urza_id)
    repository.get_form_by_id.return_value = schema_form
    draft = _record(user_id, schema_form.id, DocumentStatus.DRAFT)
    approved = _record(user_id, schema_form.id, DocumentStatus.APPROVED)
    repository.get_unfinished.return_value = None

    assert await service.get_available_actions(user_id, draft) == {
        "edit", "submit", "delete",
    }
    assert await service.get_available_actions(user_id, approved) == {
        "new_record", "delete",
    }


@pytest.mark.asyncio
async def test_get_available_actions_excludes_soft_deleted_record() -> None:
    service, repository, _, user_id, urza_id = _service(UserRole.ADMIN)
    record = _record(user_id, uuid7(), DocumentStatus.APPROVED)
    record.deleted_at = datetime.now(timezone.utc)

    assert await service.get_available_actions(user_id, record) == set()
    repository.get_form_by_id.assert_not_awaited()
