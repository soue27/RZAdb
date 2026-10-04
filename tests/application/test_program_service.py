from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.programs.service import ProgramService
from app.domain.enums import DocumentStatus, ProgramType, UserRole
from app.domain.program import Program


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_urza = AsyncMock()
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
def service(
    repository,
    access_service,
    user_repository,
    urza_repository,
):
    return ProgramService(
        repository=repository,
        access_service=access_service,
        user_repository=user_repository,
        urza_repository=urza_repository,
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
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()
    task_id = uuid7()

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
    )

    actions = await service.get_available_actions(
        user_id=uuid7(),
        program=program,
    )

    assert actions == {"submit"}


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
    )

    actions = await service.get_available_actions(
        user_id=uuid7(),
        program=program,
    )

    assert actions == set()


