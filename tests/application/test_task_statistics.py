from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.tasks.statistics import TaskStatisticsService
from app.domain.enums import TaskStatus, UserRole


class FakeUserRepository:
    def __init__(self, user):
        self.user = user

    async def get_by_id(self, user_id):
        return self.user


class FakeAccessService:
    def __init__(self, user, roots=()):
        self.user_repository = FakeUserRepository(user)
        self.roots = roots

    async def get_accessible_enterprise_roots(self, user_id):
        return self.roots


class FakeEnterpriseRepository:
    def __init__(self, enterprises):
        self.enterprises = enterprises

    async def get_by_id(self, enterprise_id):
        return next(
            (enterprise for enterprise in self.enterprises if enterprise.id == enterprise_id),
            None,
        )

    async def get_all_active(self):
        return self.enterprises

    async def get_all_for_access_scope(self):
        return self.enterprises


class FakeStatisticsRepository:
    def __init__(self, statuses, overdue):
        self.statuses = statuses
        self.overdue = overdue
        self.calls = []

    async def count_dashboard_statuses(self, **kwargs):
        self.calls.append(kwargs)
        return self.statuses, self.overdue


def _enterprise(enterprise_id, parent_id=None):
    return SimpleNamespace(id=enterprise_id, parent_id=parent_id, deleted_at=None)


def _service(user, *, roots=(), enterprises=(), task_statuses=None,
             task_overdue=0, inspection_statuses=None, inspection_overdue=0):
    task_repository = FakeStatisticsRepository(task_statuses or {}, task_overdue)
    inspection_repository = FakeStatisticsRepository(
        inspection_statuses or {}, inspection_overdue
    )
    service = TaskStatisticsService(
        task_repository=task_repository,
        inspection_repository=inspection_repository,
        enterprise_repository=FakeEnterpriseRepository(enterprises),
        access_service=FakeAccessService(user, roots),
    )
    return service, task_repository, inspection_repository


@pytest.mark.asyncio
async def test_engineer_statistics_include_assigned_work_and_inspections_only():
    enterprise_id = uuid4()
    user = SimpleNamespace(
        id=uuid4(),
        role=UserRole.ENGINEER,
        enterprise_id=enterprise_id,
        active=True,
        deleted_at=None,
    )
    service, tasks, inspections = _service(
        user,
        enterprises=[_enterprise(enterprise_id)],
        task_statuses={
            TaskStatus.CREATED: 1,
            TaskStatus.ASSIGNED: 2,
            TaskStatus.IN_PROGRESS: 3,
            TaskStatus.UNDER_REVIEW: 4,
            TaskStatus.CLOSED: 5,
            TaskStatus.REJECTED: 6,
        },
        task_overdue=2,
        inspection_statuses={
            TaskStatus.IN_PROGRESS: 1,
            TaskStatus.UNDER_REVIEW: 2,
            TaskStatus.CLOSED: 3,
            TaskStatus.REJECTED: 4,
        },
        inspection_overdue=1,
    )

    result = await service.get_for_user(user.id)

    assert result == {
        "in_progress": 7,
        "under_review": 6,
        "overdue": 3,
        "closed": 8,
    }
    for repository in (tasks, inspections):
        assert repository.calls[0]["user_id"] == user.id
        assert repository.calls[0]["role"] is UserRole.ENGINEER
        assert repository.calls[0]["enterprise_ids"] == {enterprise_id}


@pytest.mark.asyncio
async def test_manager_scope_is_own_department_only():
    department_id, child_id, other_id = uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(
        id=uuid4(), role=UserRole.MANAGER, enterprise_id=department_id,
        active=True, deleted_at=None,
    )
    service, tasks, _ = _service(
        user,
        enterprises=[
            _enterprise(department_id),
            _enterprise(child_id, department_id),
            _enterprise(other_id),
        ],
    )

    await service.get_for_user(user.id)

    assert tasks.calls[0]["enterprise_ids"] == {department_id}


@pytest.mark.asyncio
async def test_specialist_scope_includes_only_accessible_hierarchy():
    root_id, child_id, other_id = uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(
        id=uuid4(), role=UserRole.SPECIALIST, enterprise_id=root_id,
        active=True, deleted_at=None,
    )
    service, tasks, _ = _service(
        user,
        roots=[_enterprise(root_id)],
        enterprises=[
            _enterprise(root_id),
            _enterprise(child_id, root_id),
            _enterprise(other_id),
        ],
    )

    await service.get_for_user(user.id)

    assert tasks.calls[0]["enterprise_ids"] == {root_id, child_id}


@pytest.mark.asyncio
async def test_inactive_user_receives_zero_counts_without_queries():
    user = SimpleNamespace(
        id=uuid4(), role=UserRole.MANAGER, enterprise_id=uuid4(),
        active=False, deleted_at=None,
    )
    service, tasks, inspections = _service(user)

    result = await service.get_for_user(user.id)

    assert result == {
        "in_progress": 0,
        "under_review": 0,
        "overdue": 0,
        "closed": 0,
    }
    assert not tasks.calls
    assert not inspections.calls


@pytest.mark.asyncio
async def test_superadmin_statistics_are_limited_to_authored_assigned_or_reviewed():
    user = SimpleNamespace(
        id=uuid4(), role=UserRole.SUPERADMIN, enterprise_id=None,
        active=True, deleted_at=None,
    )
    enterprise_id = uuid4()
    service, tasks, inspections = _service(
        user,
        enterprises=[_enterprise(enterprise_id)],
    )

    await service.get_for_user(user.id)

    assert tasks.calls[0]["enterprise_ids"] == {enterprise_id}
    assert tasks.calls[0]["role"] is UserRole.SUPERADMIN
    assert inspections.calls[0]["role"] is UserRole.SUPERADMIN
