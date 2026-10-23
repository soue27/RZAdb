from datetime import UTC, datetime
from uuid import UUID

from app.application.access.service import AccessService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.inspections.repository import InspectionTaskRepository
from app.application.tasks.repository import TaskRepository
from app.application.work_items.service import (
    InspectionTaskWorkItemSource,
    WorkItemService,
)
from app.domain.enums import TaskStatus, UserRole


class TaskStatisticsService:
    """Builds dashboard counts from visible work and task aggregates."""

    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        inspection_repository: InspectionTaskRepository,
        enterprise_repository: EnterpriseRepository,
        access_service: AccessService,
        work_item_service: WorkItemService,
        inspection_work_item_source: InspectionTaskWorkItemSource,
    ) -> None:
        self.task_repository = task_repository
        self.inspection_repository = inspection_repository
        self.enterprise_repository = enterprise_repository
        self.access_service = access_service
        self.work_item_service = work_item_service
        self.inspection_work_item_source = inspection_work_item_source

    async def get_for_user(self, user_id: UUID) -> dict[str, int]:
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return self._empty_stats()

        enterprise_ids = await self._accessible_enterprise_ids(user)
        now = datetime.now(UTC)
        task_statuses, task_overdue = await self.task_repository.count_dashboard_statuses(
            user_id=user_id,
            role=user.role,
            enterprise_ids=enterprise_ids,
            now=now,
        )
        inspection_statuses, inspection_overdue = (
            await self.inspection_repository.count_dashboard_statuses(
                user_id=user_id,
                role=user.role,
                enterprise_ids=enterprise_ids,
                now=now,
            )
        )

        statuses = task_statuses.copy()
        for status, count in inspection_statuses.items():
            statuses[status] = statuses.get(status, 0) + count

        work_items = await self.work_item_service.list_for_user(user_id)
        inspection_items = await self.inspection_work_item_source.list_for_user(
            user_id,
            role=user.role,
        )
        under_review = sum(
            item.tab == "review" for item in (*work_items, *inspection_items)
        )

        return {
            "in_progress": sum(
                statuses.get(status, 0)
                for status in (
                    TaskStatus.CREATED,
                    TaskStatus.ASSIGNED,
                    TaskStatus.IN_PROGRESS,
                )
            ),
            "under_review": under_review,
            "overdue": task_overdue + inspection_overdue,
            "closed": statuses.get(TaskStatus.CLOSED, 0),
        }

    async def _accessible_enterprise_ids(self, user) -> set[UUID]:
        if user.role in {UserRole.MANAGER, UserRole.ADMIN, UserRole.ENGINEER}:
            if user.enterprise_id is None:
                return set()
            enterprise = await self.enterprise_repository.get_by_id(user.enterprise_id)
            if enterprise is None:
                return set()
            return {user.enterprise_id}

        if user.role is UserRole.SUPERADMIN:
            enterprises = await self.enterprise_repository.get_all_for_access_scope()
            return {enterprise.id for enterprise in enterprises}

        enterprises = await self.enterprise_repository.get_all_active()
        roots = await self.access_service.get_accessible_enterprise_roots(user.id)
        root_ids = {root.id for root in roots}
        if not root_ids:
            return set()

        # Specialist access follows the existing parent-child hierarchy.
        accessible = set(root_ids)
        changed = True
        while changed:
            previous_size = len(accessible)
            accessible.update(
                enterprise.id
                for enterprise in enterprises
                if enterprise.parent_id in accessible
            )
            changed = len(accessible) != previous_size
        return accessible

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        return {
            "in_progress": 0,
            "under_review": 0,
            "overdue": 0,
            "closed": 0,
        }
