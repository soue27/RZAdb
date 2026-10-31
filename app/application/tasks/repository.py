from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.domain.connection import Connection
from app.domain.enums import TaskStatus, UserRole
from app.domain.maintenance import TORecord
from app.domain.program import Program
from app.domain.rza_instruction import RZAInstructionVersion
from app.domain.schema import SchemaRecord
from app.domain.selectivity_scheme import SelectivitySchemeVersion
from app.domain.settings_record import SettingsRecord
from app.domain.substation import Substation
from app.domain.task import Task
from app.domain.task_history import TaskHistory
from app.domain.urza import URZA


class TaskRepository:
    """Работа с задачами через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, task: Task) -> Task:
        # Репозиторий только сохраняет сущность; бизнес-правила находятся в сервисе.
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def refresh_for_mutation(self, task: Task) -> Task:
        """Reload task state after its owner row has been locked."""
        await self.session.refresh(task)
        return task

    async def get_active_by_id(self, task_id: UUID) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.substation),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.substation),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .where(Task.deleted_at.is_(None))
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return list(result.scalars().all())


    async def list_for_email_digest_engineer(
        self,
        user_id: UUID,
    ) -> list[Task]:
        """Возвращает активные задачи инженера для email-сводки."""
        statuses = (
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
        )

        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.substation),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .where(
                Task.assigned_to == user_id,
                Task.deleted_at.is_(None),
                Task.status.in_(statuses),
            )
            .order_by(
                Task.deadline_at.asc().nulls_last(),
                Task.created_at.desc(),
                Task.id.desc(),
            )
        )
        return list(result.scalars().all())


    async def list_for_email_digest_manager(
        self,
        enterprise_id: UUID,
    ) -> list[Task]:
        """Возвращает активные задачи предприятия для email-сводки руководителя."""
        statuses = (
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
        )

        task_urza = aliased(URZA)
        task_connection = aliased(Connection)
        urza_substation = aliased(Substation)
        direct_substation = aliased(Substation)

        visible_in_enterprise = or_(
            and_(
                Task.urza_id.is_not(None),
                urza_substation.enterprise_id == enterprise_id,
            ),
            and_(
                Task.substation_id.is_not(None),
                direct_substation.enterprise_id == enterprise_id,
            ),
        )

        query = (
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.substation),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .outerjoin(task_urza, Task.urza_id == task_urza.id)
            .outerjoin(
                task_connection,
                task_urza.connection_id == task_connection.id,
            )
            .outerjoin(
                urza_substation,
                task_connection.substation_id == urza_substation.id,
            )
            .outerjoin(
                direct_substation,
                Task.substation_id == direct_substation.id,
            )
            .where(
                Task.deleted_at.is_(None),
                Task.status.in_(statuses),
                visible_in_enterprise,
            )
            .order_by(
                Task.deadline_at.asc().nulls_last(),
                Task.created_at.desc(),
                Task.id.desc(),
            )
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())


    async def count_dashboard_statuses(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        enterprise_ids: set[UUID],
        now: datetime,
    ) -> tuple[dict[TaskStatus, int], int]:
        if not enterprise_ids:
            return {}, 0

        statuses = (
            TaskStatus.CREATED,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
            TaskStatus.COMPLETED,
            TaskStatus.CLOSED,
            TaskStatus.REJECTED,
        )
        status_counts = [
            func.count(case((Task.status == status, Task.id)))
            for status in statuses
        ]
        overdue = func.count(
            case(
                (
                    and_(
                        Task.deadline_at.is_not(None),
                        Task.deadline_at < now,
                        Task.status.not_in({TaskStatus.CLOSED, TaskStatus.REJECTED}),
                    ),
                    Task.id,
                )
            )
        )
        task_urza = aliased(URZA)
        task_connection = aliased(Connection)
        urza_substation = aliased(Substation)
        direct_substation = aliased(Substation)
        visible_in_enterprise = or_(
            and_(
                Task.urza_id.is_not(None),
                urza_substation.enterprise_id.in_(enterprise_ids),
            ),
            and_(
                Task.substation_id.is_not(None),
                direct_substation.enterprise_id.in_(enterprise_ids),
            ),
        )
        query = (
            select(*status_counts, overdue)
            .outerjoin(task_urza, Task.urza_id == task_urza.id)
            .outerjoin(task_connection, task_urza.connection_id == task_connection.id)
            .outerjoin(urza_substation, task_connection.substation_id == urza_substation.id)
            .outerjoin(direct_substation, Task.substation_id == direct_substation.id)
            .where(Task.deleted_at.is_(None), visible_in_enterprise)
        )
        if role is UserRole.ENGINEER:
            query = query.where(Task.assigned_to == user_id)
        elif role is UserRole.SUPERADMIN:
            reviewed = select(TaskHistory.id).where(
                TaskHistory.task_id == Task.id,
                TaskHistory.actor_id == user_id,
                TaskHistory.event_type.in_({"review_approved", "review_rejected"}),
            ).exists()
            query = query.where(
                or_(Task.created_by == user_id, Task.assigned_to == user_id, reviewed)
            )

        row = (await self.session.execute(query)).one()
        return dict(zip(statuses, row[:-1], strict=True)), row[-1]
    async def get_history(self, task_id: UUID) -> list[TaskHistory]:
        result = await self.session.execute(
            select(TaskHistory)
            .options(
                selectinload(TaskHistory.actor),
                selectinload(TaskHistory.previous_assignee),
                selectinload(TaskHistory.new_assignee),
            )
            .where(TaskHistory.task_id == task_id)
            .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
        )
        return list(result.scalars().all())


    async def list_reviewed_task_ids(self, actor_id: UUID) -> set[UUID]:
        result = await self.session.scalars(
            select(TaskHistory.task_id)
            .where(
                TaskHistory.actor_id == actor_id,
                TaskHistory.event_type.in_(
                    {"review_approved", "review_rejected"}
                ),
            )
            .distinct()
        )
        return set(result.all())


    async def save(self, task: Task) -> Task:
        # flush фиксирует изменения в текущей транзакции, но commit остаётся за сервисом.
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_otd_version_by_task_id(self, task_id: UUID):
        """Находит версию ОТД, созданную в рамках указанной задачи."""
        from app.domain.otd import OTDVersion

        result = await self.session.execute(
            select(OTDVersion).where(
                OTDVersion.task_id == task_id,
                OTDVersion.deleted_at.is_(None),
            )
        )

        return result.scalar_one_or_none()

    async def get_settings_record_by_task_id(
            self,
            task_id: UUID,
    ) -> SettingsRecord | None:
        """Находит запись уставок, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(SettingsRecord).where(
                SettingsRecord.task_id == task_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_schema_record_by_task_id(
            self,
            task_id: UUID,
    ) -> SchemaRecord | None:
        """Находит запись схем, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(SchemaRecord).where(
                SchemaRecord.task_id == task_id,
                SchemaRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_program_by_task_id(
            self,
            task_id: UUID,
    ) -> Program | None:
        """Находит программу, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(Program).where(Program.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_to_record_by_task_id(
            self,
            task_id: UUID,
    ) -> TORecord | None:
        """Находит запись ТО, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(TORecord).where(
                TORecord.task_id == task_id,
                TORecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_substation_instruction_version_by_task_id(
        self, task_id: UUID
    ) -> RZAInstructionVersion | None:
        result = await self.session.execute(
            select(RZAInstructionVersion).where(
                RZAInstructionVersion.task_id == task_id,
                RZAInstructionVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_selectivity_version_by_task_id(
        self, task_id: UUID
    ) -> SelectivitySchemeVersion | None:
        result = await self.session.execute(
            select(SelectivitySchemeVersion).where(
                SelectivitySchemeVersion.task_id == task_id,
                SelectivitySchemeVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


    async def get_assignment_actor(
        self,
        *,
        task_id: UUID,
        assignee_id: UUID,
    ) -> UUID | None:
        """Возвращает автора последнего назначения указанного исполнителя."""
        result = await self.session.scalar(
            select(TaskHistory.actor_id)
            .where(
                TaskHistory.task_id == task_id,
                or_(
                    TaskHistory.event_type == "assigned",
                    and_(
                        TaskHistory.event_type == "reassigned",
                        TaskHistory.new_assignee_id == assignee_id,
                    ),
                ),
            )
            .order_by(
                TaskHistory.created_at.desc(),
                TaskHistory.id.desc(),
            )
            .limit(1)
        )
        return result

