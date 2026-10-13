from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.programs.service import ProgramService
from app.domain.enums import (
    DocumentStatus,
    ProgramType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.program import Program


@pytest.mark.asyncio
async def test_list_standalone_work_items_includes_only_author_drafts(
    service,
    repository,
    user_repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    user = SimpleNamespace(
        id=user_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
    user_repository.get_by_id.return_value = user
    access_service.can_access_urza.return_value = True
    own_draft = SimpleNamespace(
        id=uuid7(),
        created_by=user_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
    )
    other_draft = SimpleNamespace(
        id=uuid7(),
        created_by=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
    )
    repository.list_standalone_work_items = AsyncMock(
        return_value=[own_draft, other_draft]
    )

    result = await service.list_standalone_work_items(user_id)

    assert result == [own_draft]


@pytest.fixture
def repository():
    repository = MagicMock()
    repository.get_by_task_id = AsyncMock(return_value=None)
    return repository



@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_urza = AsyncMock()
    return service


@pytest.fixture
def task_service():
    service = MagicMock()
    service.complete_task = AsyncMock()
    service.submit_for_review = AsyncMock()
    service.close_task = AsyncMock()
    service.return_for_revision = AsyncMock()
    return service


@pytest.fixture
def user_repository():
    repository = MagicMock()
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(role=UserRole.ENGINEER),
    )
    return repository


@pytest.fixture
def urza_repository():
    repository = MagicMock()
    repository.get_by_id = AsyncMock()
    return repository



@pytest.fixture
def task_repository():
    repository = MagicMock()
    repository.get_by_id = AsyncMock()
    return repository




@pytest.fixture
def service(
    repository,
    access_service,
    user_repository,
    urza_repository,
    task_repository,
    task_service,
):
    return ProgramService(
        repository=repository,
        access_service=access_service,
        user_repository=user_repository,
        urza_repository=urza_repository,
        task_repository=task_repository,
        task_service=task_service,
    )



@pytest.mark.asyncio
async def test_get_by_urza_returns_programs(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    programs = [
        MagicMock(spec=Program),
        MagicMock(spec=Program),
    ]

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=programs,
    )

    result = await service.get_by_urza(
        user_id,
        urza_id,
    )

    assert result == programs
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_awaited_once_with(
        urza_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_urza_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_urza(
            user_id,
            urza_id,
        )

    repository.get_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_returns_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = MagicMock(spec=Program)

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=program,
    )

    result = await service.get_by_id(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_id.assert_awaited_once_with(
        program_id,
    )


@pytest.mark.asyncio
async def test_get_by_id_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_id(
            user_id,
            program_id,
            urza_id,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_task_returns_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    program = MagicMock(spec=Program)

    access_service.can_access_urza.return_value = True
    repository.get_by_task_id = AsyncMock(
        return_value=program,
    )

    result = await service.get_by_task(
        user_id,
        task_id,
        urza_id,
    )

    assert result is program
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_task_id.assert_awaited_once_with(
        task_id,
    )


@pytest.mark.asyncio
async def test_get_by_task_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_task_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_task(
            user_id,
            task_id,
            urza_id,
        )

    repository.get_by_task_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_program(
    service,
    repository,
    access_service,
    user_repository,
    task_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()
    task_id = uuid7()

    task_repository.get_by_id.return_value = SimpleNamespace(
        deleted_at=None,
        work_type=TaskWorkType.PROGRAM,
        urza_id=urza_id,
        assigned_to=user_id,
        status=TaskStatus.IN_PROGRESS,
    )

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="ПР-001",
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        task_id=task_id,
    )

    assert result.created_by == user_id
    assert result.updated_by == user_id

    assert isinstance(result, Program)
    assert result.urza_id == urza_id
    assert result.program_type == ProgramType.WORK
    assert result.program_number == "ПР-001"
    assert result.scan_file_id == scan_file_id
    assert result.editable_file_id == editable_file_id
    assert result.task_id == task_id
    assert result.status == DocumentStatus.DRAFT

    repository.add.assert_awaited_once_with(result)
    user_repository.get_by_id.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_create_program_without_editable_file(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        program_type=ProgramType.COMMISSIONING,
        program_number="ВВ-001",
        scan_file_id=scan_file_id,
    )

    assert result.program_type == ProgramType.COMMISSIONING
    assert result.editable_file_id is None
    assert result.task_id is None
    assert result.status == DocumentStatus.DRAFT

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_supports_all_program_types(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    for program_type in ProgramType:
        result = await service.create(
            user_id=uuid7(),
            urza_id=uuid7(),
            program_type=program_type,
            program_number=f"TEST-{program_type.value}",
            scan_file_id=uuid7(),
        )

        assert result.program_type == program_type

    assert repository.add.await_count == len(ProgramType)


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (UserRole.ENGINEER, DocumentStatus.DRAFT),
        (UserRole.ADMIN, DocumentStatus.DRAFT),
        (UserRole.SUPERADMIN, DocumentStatus.DRAFT),
        (UserRole.MANAGER, DocumentStatus.APPROVED),
    ],
)
@pytest.mark.asyncio
async def test_create_program_sets_initial_status_by_role(
    service,
    repository,
    user_repository,
    access_service,
    role,
    expected_status,
):
    user_id = uuid7()
    access_service.can_access_urza.return_value = True
    user_repository.get_by_id.return_value = SimpleNamespace(role=role)
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=uuid7(),
        program_type=ProgramType.WORK,
        program_number="ПР-002",
        scan_file_id=uuid7(),
    )

    assert result.status == expected_status
    user_repository.get_by_id.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_create_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.add = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            program_type=ProgramType.WORK,
            program_number="ПР-001",
            scan_file_id=uuid7(),
        )

    repository.add.assert_not_awaited()



@pytest.mark.asyncio
async def test_update_program(service, repository, access_service, user_repository):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    old_scan_id = uuid7()
    new_scan_id = uuid7()
    old_editable_id = uuid7()
    new_editable_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        program_type=ProgramType.WORK,
        program_number="OLD-001",
        scan_file_id=old_scan_id,
        editable_file_id=old_editable_id,
        updated_by=None,
    )
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock(return_value=program)
    access_service.can_access_urza.return_value = True
    user_repository.get_by_id.return_value = SimpleNamespace(
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    result = await service.update(
        user_id=user_id,
        program_id=program_id,
        urza_id=urza_id,
        program_type=ProgramType.COMMISSIONING,
        program_number="  NEW-001  ",
        scan_file_id=new_scan_id,
        editable_file_id=new_editable_id,
    )

    assert result.program_type is ProgramType.COMMISSIONING
    assert result.program_number == "NEW-001"
    assert result.scan_file_id == new_scan_id
    assert result.editable_file_id == new_editable_id
    assert result.updated_by == user_id
    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_update_program_keeps_files_when_ids_not_provided(
    service, repository, access_service, user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        program_type=ProgramType.WORK,
        program_number="OLD-001",
        scan_file_id=uuid7(),
        editable_file_id=uuid7(),
        updated_by=None,
    )
    original_scan_id = program.scan_file_id
    original_editable_id = program.editable_file_id

    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock(return_value=program)
    access_service.can_access_urza.return_value = True
    user_repository.get_by_id.return_value = SimpleNamespace(
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    await service.update(
        user_id=user_id,
        program_id=program.id,
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="NEW-001",
    )

    assert program.scan_file_id == original_scan_id
    assert program.editable_file_id == original_editable_id


@pytest.mark.asyncio
async def test_update_program_removes_editable_file(
    service, repository, access_service, user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        program_type=ProgramType.WORK,
        program_number="OLD-001",
        scan_file_id=uuid7(),
        editable_file_id=uuid7(),
        updated_by=None,
    )

    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock(return_value=program)
    access_service.can_access_urza.return_value = True
    user_repository.get_by_id.return_value = SimpleNamespace(
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    await service.update(
        user_id=user_id,
        program_id=program.id,
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="NEW-001",
        remove_editable_file=True,
    )

    assert program.editable_file_id is None
    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_update_program_rejects_approved_program(
    service, repository, access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.APPROVED,
        program_type=ProgramType.WORK,
        program_number="OLD-001",
        scan_file_id=uuid7(),
        editable_file_id=None,
        updated_by=None,
    )

    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    access_service.can_access_urza.return_value = True

    with pytest.raises(ValueError, match="только программу"):
        await service.update(
            user_id=user_id,
            program_id=program.id,
            urza_id=urza_id,
            program_type=ProgramType.WORK,
            program_number="NEW-001",
        )

    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_program_rejects_empty_number(
    service, repository, access_service, user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        program_type=ProgramType.WORK,
        program_number="OLD-001",
        scan_file_id=uuid7(),
        editable_file_id=None,
        updated_by=None,
    )

    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    access_service.can_access_urza.return_value = True
    user_repository.get_by_id.return_value = SimpleNamespace(
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )

    with pytest.raises(ValueError, match="не может быть пустым"):
        await service.update(
            user_id=user_id,
            program_id=program.id,
            urza_id=urza_id,
            program_type=ProgramType.WORK,
            program_number="   ",
        )

    repository.save.assert_not_awaited()



@pytest.mark.asyncio
async def test_submit_for_review_changes_status_to_under_review(
    service,
    repository,
    access_service,
    user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=program,
    )
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            role=UserRole.ENGINEER,
        ),
    )
    repository.save = AsyncMock()

    result = await service.submit_for_review(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    assert program.status is DocumentStatus.UNDER_REVIEW
    assert program.updated_by == user_id

    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_submit_for_review_rejects_approved_program(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=program_id,
            urza_id=urza_id,
            status=DocumentStatus.APPROVED,
        ),
    )

    with pytest.raises(
        ValueError,
        match="На согласование можно отправить только черновик",
    ):
        await service.submit_for_review(
            user_id,
            program_id,
            urza_id,
        )

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.ENGINEER,
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    ],
)
async def test_submit_for_review_allows_document_author_roles(
    service,
    repository,
    access_service,
    user_repository,
    role,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(role=role),
    )
    repository.save = AsyncMock()

    await service.submit_for_review(
        user_id,
        program_id,
        urza_id,
    )

    assert program.status is DocumentStatus.UNDER_REVIEW


@pytest.mark.asyncio
async def test_submit_for_review_denies_manager(
    service,
    repository,
    access_service,
    user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            role=UserRole.MANAGER,
        ),
    )

    with pytest.raises(
        PermissionError,
        match="Отправлять программу на согласование",
    ):
        await service.submit_for_review(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_approve_allows_manager_of_urza_department(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    enterprise_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=enterprise_id,
    )

    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=enterprise_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)

    result = await service.approve(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    assert program.status is DocumentStatus.APPROVED
    assert program.updated_by == user_id

    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_approve_denies_manager_of_another_department(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    manager_department_id = uuid7()
    urza_department_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=manager_department_id,
        task_id=None,
    )

    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=urza_department_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)

    with pytest.raises(
        PermissionError,
        match="Manager не отвечает за данный Production Department",
    ):
        await service.approve(
            user_id,
            program_id,
            urza_id,
        )

    repository.save.assert_not_called()


@pytest.mark.asyncio
async def test_approve_denies_engineer(
    service,
    repository,
    access_service,
    user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
    )

    with pytest.raises(
        PermissionError,
        match="Согласовывать программы может только Manager",
    ):
        await service.approve(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_approve_denies_inactive_manager(
    service,
    repository,
    access_service,
    user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            role=UserRole.MANAGER,
            active=False,
            deleted_at=None,
        ),
    )

    with pytest.raises(
        PermissionError,
        match="Пользователь неактивен",
    ):
        await service.approve(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_approve_rejects_draft(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=program_id,
            urza_id=urza_id,
            status=DocumentStatus.DRAFT,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Утвердить можно только программу на согласовании",
    ):
        await service.approve(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_return_to_draft_allows_manager_of_urza_department(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    enterprise_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=enterprise_id,
    )

    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=enterprise_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)

    result = await service.return_to_draft(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    assert program.status is DocumentStatus.DRAFT
    assert program.updated_by == user_id

    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_return_to_draft_denies_manager_of_another_department(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    manager_department_id = uuid7()
    urza_department_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=manager_department_id,
    )

    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=urza_department_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)

    with pytest.raises(
        PermissionError,
        match="Manager не отвечает за данный Production Department",
    ):
        await service.return_to_draft(
            user_id,
            program_id,
            urza_id,
        )

    repository.save.assert_not_called()


@pytest.mark.asyncio
async def test_return_to_draft_denies_engineer(
    service,
    repository,
    access_service,
    user_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=None,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        ),
    )

    with pytest.raises(
        PermissionError,
        match="Согласовывать программы может только Manager",
    ):
        await service.return_to_draft(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_return_to_draft_rejects_draft(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=program_id,
            urza_id=urza_id,
            status=DocumentStatus.DRAFT,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Вернуть на доработку можно только программу на согласовании",
    ):
        await service.return_to_draft(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_return_to_draft_rejects_approved(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=program_id,
            urza_id=urza_id,
            status=DocumentStatus.APPROVED,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Вернуть на доработку можно только программу на согласовании",
    ):
        await service.return_to_draft(
            user_id,
            program_id,
            urza_id,
        )


@pytest.mark.asyncio
async def test_get_available_actions_draft_engineer(
    service,
    user_repository,
):
    user_repository.get_by_id.return_value = SimpleNamespace(
        active=True,
        deleted_at=None,
        role=UserRole.ENGINEER,
    )

    program = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        status=DocumentStatus.DRAFT,
        task_id=None,
    )

    actions = await service.get_available_actions(
        user_id=uuid7(),
        program=program,
    )

    assert actions == {"submit", "edit"}


@pytest.mark.asyncio
async def test_get_available_actions_draft_manager(
    service,
    user_repository,
):
    user_repository.get_by_id.return_value = SimpleNamespace(
        active=True,
        deleted_at=None,
        role=UserRole.MANAGER,
    )

    program = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        status=DocumentStatus.DRAFT,
        task_id=None,
    )

    actions = await service.get_available_actions(
        user_id=uuid7(),
        program=program,
    )

    assert actions == set()


@pytest.mark.asyncio
async def test_get_available_actions_under_review_manager_same_department(
    service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()
    enterprise_id = uuid7()
    urza_id = uuid7()

    user_repository.get_by_id.return_value = SimpleNamespace(
        active=True,
        deleted_at=None,
        role=UserRole.MANAGER,
        enterprise_id=enterprise_id,
    )

    urza_repository.get_by_id.return_value = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=enterprise_id,
            ),
        ),
    )

    program = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        task_id=None,
    )

    actions = await service.get_available_actions(
        user_id=user_id,
        program=program,
    )

    assert actions == {"approve", "return"}


@pytest.mark.asyncio
async def test_get_available_actions_under_review_manager_other_department(
    service,
    user_repository,
    urza_repository,
):
    user_id = uuid7()

    user_repository.get_by_id.return_value = SimpleNamespace(
        active=True,
        deleted_at=None,
        role=UserRole.MANAGER,
        enterprise_id=uuid7(),
    )

    urza_repository.get_by_id.return_value = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=uuid7(),
            ),
        ),
    )

    program = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        status=DocumentStatus.UNDER_REVIEW,
        task_id=None,
    )

    actions = await service.get_available_actions(
        user_id=user_id,
        program=program,
    )

    assert actions == set()


@pytest.mark.asyncio
async def test_get_available_actions_approved(
    service,
    user_repository,
):
    user_repository.get_by_id.return_value = SimpleNamespace(
        active=True,
        deleted_at=None,
        role=UserRole.MANAGER,
        enterprise_id=uuid7(),
    )

    program = SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        status=DocumentStatus.APPROVED,
        task_id=None,
    )

    actions = await service.get_available_actions(
        user_id=uuid7(),
        program=program,
    )

    assert actions == set()



@pytest.mark.asyncio
async def test_submit_for_review_updates_linked_task(
    service,
    repository,
    access_service,
    user_repository,
    task_repository,
    task_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    task_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.DRAFT,
        updated_by=None,
        task_id=task_id,
    )
    task = SimpleNamespace(
        id=task_id,
        urza_id=urza_id,
        work_type=TaskWorkType.PROGRAM,
        assigned_to=user_id,
        deleted_at=None,
        status=TaskStatus.IN_PROGRESS,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    user_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(role=UserRole.ENGINEER),
    )
    task_repository.get_by_id = AsyncMock(return_value=task)

    result = await service.submit_for_review(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    assert program.status is DocumentStatus.UNDER_REVIEW

    task_repository.get_by_id.assert_awaited_once_with(task_id)
    task_service.complete_task.assert_awaited_once_with(
        task=task,
        actor_id=user_id,
    )
    task_service.submit_for_review.assert_awaited_once_with(
        task=task,
        actor_id=user_id,
    )
    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_approve_closes_linked_task(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
    task_repository,
    task_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    task_id = uuid7()
    enterprise_id = uuid7()

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=task_id,
    )
    task = SimpleNamespace(
        id=task_id,
        urza_id=urza_id,
        work_type=TaskWorkType.PROGRAM,
        deleted_at=None,
        status=TaskStatus.UNDER_REVIEW,
    )
    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=enterprise_id,
    )
    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=enterprise_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)
    task_repository.get_by_id = AsyncMock(return_value=task)

    result = await service.approve(
        user_id,
        program_id,
        urza_id,
    )

    assert result is program
    assert program.status is DocumentStatus.APPROVED

    task_repository.get_by_id.assert_awaited_once_with(task_id)
    task_service.close_task.assert_awaited_once_with(
        task=task,
        actor_id=user_id,
    )
    repository.save.assert_awaited_once_with(program)


@pytest.mark.asyncio
async def test_return_to_draft_returns_linked_task_for_revision(
    service,
    repository,
    access_service,
    user_repository,
    urza_repository,
    task_repository,
    task_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    program_id = uuid7()
    task_id = uuid7()
    enterprise_id = uuid7()
    comment = "Исправить параметры программы."

    program = SimpleNamespace(
        id=program_id,
        urza_id=urza_id,
        status=DocumentStatus.UNDER_REVIEW,
        updated_by=None,
        task_id=task_id,
    )
    task = SimpleNamespace(
        id=task_id,
        urza_id=urza_id,
        work_type=TaskWorkType.PROGRAM,
        deleted_at=None,
        status=TaskStatus.UNDER_REVIEW,
    )
    manager = SimpleNamespace(
        role=UserRole.MANAGER,
        active=True,
        deleted_at=None,
        enterprise_id=enterprise_id,
    )
    urza = SimpleNamespace(
        connection=SimpleNamespace(
            substation=SimpleNamespace(
                enterprise_id=enterprise_id,
            ),
        ),
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(return_value=program)
    repository.save = AsyncMock()
    user_repository.get_by_id = AsyncMock(return_value=manager)
    urza_repository.get_by_id = AsyncMock(return_value=urza)
    task_repository.get_by_id = AsyncMock(return_value=task)

    result = await service.return_to_draft(
        user_id,
        program_id,
        urza_id,
        comment=comment,
    )

    assert result is program
    assert program.status is DocumentStatus.DRAFT

    task_repository.get_by_id.assert_awaited_once_with(task_id)
    task_service.return_for_revision.assert_awaited_once_with(
        task=task,
        actor_id=user_id,
        comment=comment,
    )
    repository.save.assert_awaited_once_with(program)
