from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.urza_instructions.service import URZAInstructionService
from app.domain.enums import DocumentStatus, UserRole
from app.domain.urza_instruction import URZAInstruction, URZAInstructionVersion


@pytest.fixture
def deps():
    repo, access, users, urzas = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    access.can_access_urza = AsyncMock(return_value=True)
    repo.get_by_urza_id = AsyncMock(return_value=None)
    repo.add_instruction = AsyncMock(side_effect=lambda x: x)
    repo.add_version = AsyncMock(side_effect=lambda x: x)
    repo.get_by_id = AsyncMock()
    repo.get_version_by_id = AsyncMock()
    repo.get_versions = AsyncMock(return_value=[])
    repo.get_current_version = AsyncMock()
    repo.get_max_version_number = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    users.get_by_id = AsyncMock()
    urzas.get_by_id = AsyncMock()
    service = URZAInstructionService(repo, access, users, urzas)
    return service, repo, access, users, urzas


def make_user(role, enterprise_id=None, active=True):
    return SimpleNamespace(role=role, enterprise_id=enterprise_id, active=active, deleted_at=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "expected"), [
    (UserRole.ENGINEER, DocumentStatus.DRAFT),
    (UserRole.ADMIN, DocumentStatus.DRAFT),
    (UserRole.SUPERADMIN, DocumentStatus.DRAFT),
    (UserRole.MANAGER, DocumentStatus.APPROVED),
])
async def test_create_first_version_assigns_role_status(deps, role, expected):
    service, repo, access, users, _ = deps
    user_id, urza_id = uuid7(), uuid7()
    users.get_by_id.return_value = make_user(role)
    instruction = await service.create(user_id, urza_id, date(2026, 1, 1), uuid7())
    version = repo.add_version.await_args.args[0]
    assert instruction.urza_id == urza_id
    assert version.version_number == 1
    assert version.status is expected


@pytest.mark.asyncio
async def test_create_instruction_rejects_duplicate(deps):
    service, repo, _, users, _ = deps
    users.get_by_id.return_value = make_user(UserRole.ENGINEER)
    repo.get_by_urza_id.return_value = SimpleNamespace(id=uuid7())
    with pytest.raises(ValueError, match="уже существует"):
        await service.create(uuid7(), uuid7(), date.today(), uuid7())
    repo.add_instruction.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_urza_checks_access(deps):
    service, repo, access, _, _ = deps
    access.can_access_urza.return_value = False
    with pytest.raises(PermissionError):
        await service.get_by_urza(uuid7(), uuid7())
    repo.get_by_urza_id.assert_not_awaited()


def setup_version(deps, status):
    service, repo, access, users, urzas = deps
    user_id, urza_id, iid, vid = uuid7(), uuid7(), uuid7(), uuid7()
    instruction = URZAInstruction(id=iid, urza_id=urza_id)
    version = URZAInstructionVersion(id=vid, urza_instruction_id=iid,
        version_number=2, status=status, effective_date=date(2026, 1, 1), scan_file_id=uuid7())
    repo.get_version_by_id.return_value = version
    repo.get_by_id.return_value = instruction
    users.get_by_id.return_value = make_user(UserRole.ENGINEER)
    urzas.get_by_id.return_value = SimpleNamespace(
        connection=SimpleNamespace(substation=SimpleNamespace(enterprise_id=uuid7())))
    return service, repo, access, users, urzas, user_id, urza_id, version


@pytest.mark.asyncio
async def test_draft_can_submit_for_review(deps):
    service, repo, _, _, _, user, urza, version = setup_version(deps, DocumentStatus.DRAFT)
    result = await service.submit_for_review(user, version.id, urza)
    assert result.status is DocumentStatus.UNDER_REVIEW
    repo.save.assert_awaited_once_with(version)


@pytest.mark.asyncio
async def test_under_review_manager_can_approve_or_return(deps):
    for method, expected in (("approve", DocumentStatus.APPROVED), ("return_to_draft", DocumentStatus.DRAFT)):
        service, repo, _, users, urzas, _, urza, version = setup_version(deps, DocumentStatus.UNDER_REVIEW)
        repo.save.reset_mock()
        enterprise = uuid7()
        users.get_by_id.return_value = make_user(UserRole.MANAGER, enterprise)
        urzas.get_by_id.return_value.connection.substation.enterprise_id = enterprise
        result = await getattr(service, method)(uuid7(), version.id, urza)
        assert result.status is expected
        assert repo.save.await_args.args == (version,)
        assert repo.save.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role,active,enterprise_matches", [
    (UserRole.ENGINEER, True, True),
    (UserRole.MANAGER, False, True),
    (UserRole.MANAGER, True, False),
])
async def test_approval_rejects_wrong_reviewer(deps, role, active, enterprise_matches):
    service, _, _, users, urzas, user, urza, version = setup_version(deps, DocumentStatus.UNDER_REVIEW)
    enterprise = uuid7()
    users.get_by_id.return_value = make_user(role, enterprise if enterprise_matches else uuid7(), active)
    urzas.get_by_id.return_value.connection.substation.enterprise_id = enterprise
    with pytest.raises(PermissionError):
        await service.approve(user, version.id, urza)


@pytest.mark.asyncio
async def test_invalid_status_transition_rejected(deps):
    service, _, _, _, _, user, urza, version = setup_version(deps, DocumentStatus.APPROVED)
    with pytest.raises(ValueError):
        await service.submit_for_review(user, version.id, urza)


@pytest.mark.asyncio
async def test_new_version_uses_max_and_preserves_approved_version(deps):
    service, repo, _, users, _, user, _, old_version = setup_version(deps, DocumentStatus.APPROVED)
    instruction = repo.get_by_id.return_value
    users.get_by_id.return_value = make_user(UserRole.ENGINEER)
    repo.get_max_version_number.return_value = 5
    created = await service.create_version(user, instruction.id, date(2026, 2, 2), uuid7())
    assert created.version_number == 6
    assert created.status is DocumentStatus.DRAFT
    assert old_version.status is DocumentStatus.APPROVED
    assert old_version.version_number == 2
    assert repo.get_max_version_number.await_args.args == (instruction.id,)


@pytest.mark.asyncio
async def test_available_actions_by_status_and_role(deps):
    service, _, _, users, urzas = deps
    user_id, enterprise = uuid7(), uuid7()
    users.get_by_id.return_value = make_user(UserRole.ENGINEER)
    draft = SimpleNamespace(status=DocumentStatus.DRAFT)
    assert await service.get_available_actions(user_id, draft) == {"submit"}
    approved = SimpleNamespace(status=DocumentStatus.APPROVED)
    assert await service.get_available_actions(user_id, approved) == {"new_version"}
    review = URZAInstructionVersion(status=DocumentStatus.UNDER_REVIEW, urza_instruction_id=uuid7())
    repo = service.repository
    repo.get_by_id.return_value = SimpleNamespace(urza_id=uuid7())
    users.get_by_id.return_value = make_user(UserRole.MANAGER, enterprise)
    urzas.get_by_id.return_value = SimpleNamespace(connection=SimpleNamespace(substation=SimpleNamespace(enterprise_id=enterprise)))
    assert await service.get_available_actions(user_id, review) == {"approve", "return"}
