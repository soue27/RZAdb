from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from uuid6 import uuid7

from app.application.settings.service import SettingsService
from app.domain.enums import DocumentStatus, UserRole
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


def make_user(role: UserRole, *, active: bool = True, deleted_at=None):
    return SimpleNamespace(
        id=uuid7(), role=role, active=active, deleted_at=deleted_at
    )


def make_record(
    form_id,
    status=DocumentStatus.DRAFT,
    *,
    user_id=None,
    signed_file_id=None,
):
    user_id = user_id or uuid7()
    return SettingsRecord(
        id=uuid7(),
        settings_form_id=form_id,
        change_date=date(2026, 9, 17),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        status=status,
        signed_form_file_id=signed_file_id or uuid7(),
        created_by=user_id,
        updated_by=user_id,
    )


def make_service(role=UserRole.ENGINEER, *, active=True, accessible=True):
    repository = MagicMock()
    for method in (
        "get_form_by_urza_id", "get_form_by_id", "get_record_by_id",
        "get_records_by_form_id", "get_current_approved", "get_unfinished", "add_form",
        "add_record", "save", "flush",
    ):
        setattr(repository, method, AsyncMock())
    access_service = MagicMock()
    access_service.can_access_urza = AsyncMock(return_value=accessible)
    access_service.user_repository = MagicMock()
    access_service.user_repository.get_by_id = AsyncMock(
        return_value=make_user(role, active=active)
    )
    return SettingsService(repository, access_service), repository, access_service


def form_for(urza_id, user_id=None):
    user_id = user_id or uuid7()
    return SettingsForm(
        id=uuid7(), urza_id=urza_id, created_by=user_id, updated_by=user_id
    )


def connect_record(service, repository, record, urza_id):
    settings_form = form_for(urza_id)
    settings_form.id = record.settings_form_id
    repository.get_record_by_id.return_value = record
    repository.get_form_by_id.return_value = settings_form
    return settings_form


@pytest.mark.asyncio
async def test_get_by_urza_returns_form_when_access_allowed():
    service, repository, access = make_service()
    urza_id = uuid7()
    settings_form = form_for(urza_id)
    repository.get_form_by_urza_id.return_value = settings_form

    assert await service.get_by_urza(uuid7(), urza_id) is settings_form
    access.can_access_urza.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_urza_returns_none_when_access_denied():
    service, repository, _ = make_service(accessible=False)
    assert await service.get_by_urza(uuid7(), uuid7()) is None
    repository.get_form_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_approved_returns_record_for_accessible_urza():
    service, repository, access = make_service()
    user_id, urza_id = uuid7(), uuid7()
    settings_form = form_for(urza_id)
    record = make_record(settings_form.id, DocumentStatus.APPROVED)
    repository.get_form_by_urza_id.return_value = settings_form
    repository.get_current_approved.return_value = record

    assert await service.get_current_approved(user_id, urza_id) is record

    access.can_access_urza.assert_awaited_once_with(user_id, urza_id)
    repository.get_form_by_urza_id.assert_awaited_once_with(urza_id)
    repository.get_current_approved.assert_awaited_once_with(settings_form.id)


@pytest.mark.asyncio
async def test_get_current_approved_does_not_return_soft_deleted_record():
    service, repository, _ = make_service()
    urza_id = uuid7()
    settings_form = form_for(urza_id)
    repository.get_form_by_urza_id.return_value = settings_form
    repository.get_current_approved.return_value = None

    assert await service.get_current_approved(uuid7(), urza_id) is None
    repository.get_current_approved.assert_awaited_once_with(settings_form.id)


@pytest.mark.asyncio
async def test_get_current_approved_returns_none_when_no_approved_record():
    service, repository, _ = make_service()
    urza_id = uuid7()
    repository.get_form_by_urza_id.return_value = form_for(urza_id)
    repository.get_current_approved.return_value = None

    assert await service.get_current_approved(uuid7(), urza_id) is None


@pytest.mark.asyncio
async def test_get_current_approved_checks_access_before_querying_form():
    service, repository, access = make_service(accessible=False)
    user_id, urza_id = uuid7(), uuid7()

    with pytest.raises(PermissionError, match="Доступ к URZA запрещён"):
        await service.get_current_approved(user_id, urza_id)

    access.can_access_urza.assert_awaited_once_with(user_id, urza_id)
    repository.get_form_by_urza_id.assert_not_awaited()
    repository.get_current_approved.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_form_success():
    service, repository, _ = make_service()
    repository.get_form_by_urza_id.return_value = None
    user_id, urza_id = uuid7(), uuid7()

    result = await service.create_form(user_id, urza_id)

    assert result.urza_id == urza_id
    assert result.created_by == user_id
    repository.add_form.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_form_rejects_existing_form():
    service, repository, _ = make_service()
    repository.get_form_by_urza_id.return_value = form_for(uuid7())
    with pytest.raises(ValueError, match="уже существует"):
        await service.create_form(uuid7(), uuid7())


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (UserRole.ENGINEER, DocumentStatus.DRAFT),
        (UserRole.MANAGER, DocumentStatus.APPROVED),
        (UserRole.ADMIN, DocumentStatus.DRAFT),
        (UserRole.SUPERADMIN, DocumentStatus.DRAFT),
    ],
)
@pytest.mark.asyncio
async def test_create_record_assigns_initial_status_and_preserves_task(
    role, expected_status
):
    service, repository, _ = make_service(role)
    urza_id, user_id, task_id = uuid7(), uuid7(), uuid7()
    repository.get_form_by_urza_id.return_value = None
    repository.get_unfinished.return_value = None

    record = await service.create_record(
        user_id, urza_id, date(2026, 9, 17), "Параметр", "1", "2", "Причина",
        uuid7(), task_id,
    )

    assert record.status is expected_status
    assert record.task_id == task_id
    assert repository.add_form.await_count == 1
    repository.add_record.assert_awaited_once_with(record)


@pytest.mark.parametrize(
    "role", [UserRole.ENGINEER, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN]
)
@pytest.mark.asyncio
async def test_each_permitted_role_can_create(role):
    service, repository, _ = make_service(role)
    repository.get_form_by_urza_id.return_value = form_for(uuid7())
    repository.get_unfinished.return_value = None
    result = await service.create_record(
        uuid7(), uuid7(), date.today(), "p", "1", "2", "r", uuid7()
    )
    assert result.status in {DocumentStatus.DRAFT, DocumentStatus.APPROVED}


@pytest.mark.asyncio
async def test_create_record_requires_signed_file():
    service, repository, _ = make_service()
    with pytest.raises(ValueError, match="формуляр.*обязателен"):
        await service.create_record(
            uuid7(), uuid7(), date.today(), "p", "1", "2", "r", None
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_record_rejects_second_unfinished():
    service, repository, _ = make_service()
    repository.get_form_by_urza_id.return_value = form_for(uuid7())
    repository.get_unfinished.return_value = make_record(uuid7())
    with pytest.raises(ValueError, match="незавершённая запись"):
        await service.create_record(
            uuid7(), uuid7(), date.today(), "p", "1", "2", "r", uuid7()
        )
    repository.add_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_record_allows_new_draft():
    service, repository, _ = make_service(UserRole.ENGINEER)
    repository.get_form_by_urza_id.return_value = form_for(uuid7())
    repository.get_unfinished.return_value = None
    record = await service.create_record(
        uuid7(), uuid7(), date.today(), "new", "", "", "", uuid7()
    )
    assert record.status is DocumentStatus.DRAFT


@pytest.mark.asyncio
async def test_create_record_translates_partial_unique_index_race():
    service, repository, _ = make_service()
    repository.get_form_by_urza_id.return_value = form_for(uuid7())
    repository.get_unfinished.return_value = None
    repository.add_record.side_effect = IntegrityError(
        "insert", {}, Exception("uq_settings_records_one_active_unfinished_per_form")
    )
    with pytest.raises(ValueError, match="незавершённая запись"):
        await service.create_record(
            uuid7(), uuid7(), date.today(), "p", "1", "2", "r", uuid7()
        )


@pytest.mark.parametrize(
    "role", [UserRole.ENGINEER, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN]
)
@pytest.mark.asyncio
async def test_update_draft_allowed_roles_preserve_required_file(role):
    service, repository, _ = make_service(role)
    urza_id, user_id = uuid7(), uuid7()
    record = make_record(uuid7(), user_id=user_id)
    connect_record(service, repository, record, urza_id)

    updated = await service.update_draft(
        user_id, urza_id, record.id, date.today(), "updated", "a", "b", "reason"
    )

    assert updated.parameter_name == "updated"
    assert updated.signed_form_file_id is not None
    repository.save.assert_awaited_once_with(record)


@pytest.mark.parametrize("status", [DocumentStatus.APPROVED, DocumentStatus.UNDER_REVIEW])
@pytest.mark.asyncio
async def test_update_rejects_non_draft(status):
    service, repository, _ = make_service()
    urza_id = uuid7()
    record = make_record(uuid7(), status)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(ValueError, match="только черновик"):
        await service.update_draft(
            uuid7(), urza_id, record.id, date.today(), "p", "1", "2", "r"
        )
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_draft_rejects_missing_existing_file():
    service, repository, _ = make_service()
    urza_id = uuid7()
    record = make_record(uuid7(), signed_file_id=uuid7())
    record.signed_form_file_id = None
    connect_record(service, repository, record, urza_id)
    with pytest.raises(ValueError, match="формуляр.*обязателен"):
        await service.update_draft(
            uuid7(), urza_id, record.id, date.today(), "p", "1", "2", "r", None
        )


@pytest.mark.parametrize(
    "role", [UserRole.ENGINEER, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN]
)
@pytest.mark.asyncio
async def test_submit_for_review_allowed_roles_and_sets_status(role):
    service, repository, _ = make_service(role)
    urza_id, user_id = uuid7(), uuid7()
    record = make_record(uuid7(), user_id=user_id)
    connect_record(service, repository, record, urza_id)
    result = await service.submit_for_review(user_id, urza_id, record.id)
    assert result.status is DocumentStatus.UNDER_REVIEW
    assert result.updated_by == user_id


@pytest.mark.parametrize(
    "status", [DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED]
)
@pytest.mark.asyncio
async def test_submit_rejects_non_draft(status):
    service, repository, _ = make_service()
    urza_id = uuid7()
    record = make_record(uuid7(), status)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(ValueError, match="только черновик"):
        await service.submit_for_review(uuid7(), urza_id, record.id)


@pytest.mark.asyncio
async def test_returned_draft_can_be_resubmitted_by_manager():
    service, repository, _ = make_service(UserRole.MANAGER)
    urza_id = uuid7()
    record = make_record(uuid7(), DocumentStatus.DRAFT)
    connect_record(service, repository, record, urza_id)
    assert (await service.submit_for_review(uuid7(), urza_id, record.id)).status is DocumentStatus.UNDER_REVIEW


@pytest.mark.asyncio
async def test_approve_by_manager():
    service, repository, _ = make_service(UserRole.MANAGER)
    urza_id, user_id = uuid7(), uuid7()
    record = make_record(uuid7(), DocumentStatus.UNDER_REVIEW, user_id=user_id)
    connect_record(service, repository, record, urza_id)
    result = await service.approve(user_id, urza_id, record.id)
    assert result.status is DocumentStatus.APPROVED
    repository.save.assert_awaited_once_with(record)


@pytest.mark.parametrize(
    "role", [UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN]
)
@pytest.mark.asyncio
async def test_non_manager_cannot_approve(role):
    service, repository, _ = make_service(role)
    urza_id = uuid7()
    record = make_record(uuid7(), DocumentStatus.UNDER_REVIEW)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(PermissionError, match="только Manager"):
        await service.approve(uuid7(), urza_id, record.id)


@pytest.mark.asyncio
async def test_inactive_manager_cannot_approve():
    service, repository, access = make_service(UserRole.MANAGER, active=False)
    urza_id = uuid7()
    record = make_record(uuid7(), DocumentStatus.UNDER_REVIEW)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(PermissionError, match="неактивен"):
        await service.approve(uuid7(), urza_id, record.id)


@pytest.mark.asyncio
async def test_manager_without_urza_access_cannot_approve_or_return():
    service, repository, access = make_service(UserRole.MANAGER, accessible=False)
    urza_id = uuid7()
    record = make_record(uuid7(), DocumentStatus.UNDER_REVIEW)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(PermissionError, match="Доступ"):
        await service.approve(uuid7(), urza_id, record.id)
    with pytest.raises(PermissionError, match="Доступ"):
        await service.return_to_draft(uuid7(), urza_id, record.id)


@pytest.mark.parametrize("status", [DocumentStatus.DRAFT, DocumentStatus.APPROVED])
@pytest.mark.asyncio
async def test_approve_rejects_wrong_status(status):
    service, repository, _ = make_service(UserRole.MANAGER)
    urza_id = uuid7()
    record = make_record(uuid7(), status)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(ValueError, match="только запись на согласовании"):
        await service.approve(uuid7(), urza_id, record.id)


@pytest.mark.asyncio
async def test_return_to_draft_by_manager():
    service, repository, _ = make_service(UserRole.MANAGER)
    urza_id, user_id = uuid7(), uuid7()
    record = make_record(uuid7(), DocumentStatus.UNDER_REVIEW, user_id=user_id)
    connect_record(service, repository, record, urza_id)
    result = await service.return_to_draft(user_id, urza_id, record.id)
    assert result.status is DocumentStatus.DRAFT


@pytest.mark.parametrize(
    "status", [DocumentStatus.DRAFT, DocumentStatus.APPROVED]
)
@pytest.mark.asyncio
async def test_return_rejects_wrong_status(status):
    service, repository, _ = make_service(UserRole.MANAGER)
    urza_id = uuid7()
    record = make_record(uuid7(), status)
    connect_record(service, repository, record, urza_id)
    with pytest.raises(ValueError, match="только запись на согласовании"):
        await service.return_to_draft(uuid7(), urza_id, record.id)


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN])
@pytest.mark.asyncio
async def test_delete_soft_deletes_without_changing_status(role):
    service, repository, _ = make_service(role)
    urza_id, user_id = uuid7(), uuid7()
    record = make_record(uuid7(), DocumentStatus.APPROVED, user_id=user_id)
    connect_record(service, repository, record, urza_id)
    await service.delete_record(user_id, urza_id, record.id)
    assert record.deleted_at is not None
    assert record.deleted_by == user_id
    assert record.status is DocumentStatus.APPROVED
    repository.save.assert_awaited_once_with(record)


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
@pytest.mark.asyncio
async def test_engineer_and_manager_cannot_delete(role):
    service, repository, _ = make_service(role)
    urza_id = uuid7()
    record = make_record(uuid7())
    connect_record(service, repository, record, urza_id)
    with pytest.raises(PermissionError, match="только ADMIN"):
        await service.delete_record(uuid7(), urza_id, record.id)
    repository.save.assert_not_awaited()


@pytest.mark.parametrize(
    ("role", "status", "expected"),
    [
        (UserRole.ENGINEER, DocumentStatus.DRAFT, {"edit", "submit"}),
        (UserRole.MANAGER, DocumentStatus.DRAFT, {"edit", "submit"}),
        (UserRole.ADMIN, DocumentStatus.DRAFT, {"edit", "submit", "delete"}),
        (UserRole.SUPERADMIN, DocumentStatus.DRAFT, {"edit", "submit", "delete"}),
        (UserRole.MANAGER, DocumentStatus.UNDER_REVIEW, {"approve", "return"}),
        (UserRole.ENGINEER, DocumentStatus.UNDER_REVIEW, set()),
        (UserRole.ADMIN, DocumentStatus.APPROVED, {"delete"}),
        (UserRole.SUPERADMIN, DocumentStatus.APPROVED, {"delete"}),
        (UserRole.MANAGER, DocumentStatus.APPROVED, set()),
    ],
)
@pytest.mark.asyncio
async def test_get_available_actions(role, status, expected):
    service, repository, _ = make_service(role)
    urza_id = uuid7()
    record = make_record(uuid7(), status)
    settings_form = connect_record(service, repository, record, urza_id)
    assert await service.get_available_actions(uuid7(), record) == expected
    assert settings_form.urza_id == urza_id


@pytest.mark.asyncio
async def test_get_available_actions_returns_empty_for_inactive_user():
    service, repository, _ = make_service(UserRole.ADMIN, active=False)
    record = make_record(uuid7())
    connect_record(service, repository, record, uuid7())
    assert await service.get_available_actions(uuid7(), record) == set()
