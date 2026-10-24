from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from uuid6 import uuid7

from app.application.access.service import AccessService
from app.application.objects.archive_repository import ArchiveRepository
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.archive_event import ArchiveEvent
from app.domain.enums import ArchiveEventType, TaskStatus, UserRole

ArchiveObjectType = Literal["substation", "connection", "urza"]
_ALLOWED_ROLES = {UserRole.SUPERADMIN, UserRole.ADMIN, UserRole.MANAGER}


@dataclass(frozen=True)
class ArchiveBlocker:
    process_type: Literal["task", "inspection"]
    process_id: UUID
    status: TaskStatus


@dataclass(frozen=True)
class ArchivePreview:
    object_type: ArchiveObjectType
    object_id: UUID
    object_ids: tuple[tuple[ArchiveObjectType, UUID], ...]
    blockers: tuple[ArchiveBlocker, ...]


class ArchiveBlockedError(ValueError):
    def __init__(self, blockers: tuple[ArchiveBlocker, ...]) -> None:
        self.blockers = blockers
        super().__init__("Архивирование невозможно: есть незавершённые процессы.")


class ArchiveService:
    """Архивирование объектов и чтение append-only истории архива."""

    def __init__(
        self,
        repository: ArchiveRepository,
        access_service: AccessService,
    ) -> None:
        repository_session = getattr(repository, "session", None)
        access_repositories = (
            access_service.user_repository,
            access_service.substation_repository,
            access_service.enterprise_repository,
            access_service.connection_repository,
            access_service.urza_repository,
        )
        if repository_session is not None and any(
            getattr(item, "session", repository_session) is not repository_session
            for item in access_repositories
        ):
            raise ValueError(
                "Архив и AccessService должны использовать одну AsyncSession."
            )
        self.repository = repository
        self.access_service = access_service

    async def preview(
        self,
        *,
        actor_id: UUID,
        object_type: ArchiveObjectType,
        object_id: UUID,
    ) -> ArchivePreview:
        await self._ensure_access(actor_id, object_type, object_id)
        target = await self._get_object(object_type, object_id)
        if target.deleted_at is not None:
            return ArchivePreview(object_type, object_id, (), ())
        objects = await self._cascade_objects(object_type, target)
        blockers = await self._blockers(object_type, target, objects)
        return ArchivePreview(
            object_type,
            object_id,
            tuple((kind, item.id) for kind, item in objects),
            tuple(blockers),
        )

    async def archive(
        self,
        *,
        actor_id: UUID,
        object_type: ArchiveObjectType,
        object_id: UUID,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> ArchivePreview:
        normalized_reason = reason.strip() if reason is not None else ""
        if not normalized_reason:
            raise ValueError("Укажите причину архивирования.")
        if len(normalized_reason) > 2000:
            raise ValueError("Причина архивирования не должна превышать 2000 символов.")

        await self._ensure_access(actor_id, object_type, object_id)
        target = await self._get_object(object_type, object_id)
        locked_objects = await self._lock_archive_chain(object_type, target)
        target = next(item for kind, item in locked_objects if kind == object_type)
        if target.deleted_at is not None:
            return ArchivePreview(object_type, object_id, (), ())

        # Re-read the branch only after all parent and child owner locks are held.
        locked_objects = await self._locked_cascade(object_type, target)
        blockers = await self._blockers(object_type, target, locked_objects)
        if blockers:
            raise ArchiveBlockedError(tuple(blockers))

        timestamp = occurred_at or datetime.now(UTC)
        operation_id = uuid7()
        events = []
        for kind, item in locked_objects:
            if item.deleted_at is not None:
                continue
            item.deleted_at = timestamp
            item.deleted_by = actor_id
            events.append(
                ArchiveEvent(
                    operation_id=operation_id,
                    event_type=ArchiveEventType.ARCHIVED,
                    actor_id=actor_id,
                    occurred_at=timestamp,
                    reason=normalized_reason,
                    **{f"{kind}_id": item.id},
                )
            )
        await self.repository.add_events(events)
        return ArchivePreview(
            object_type,
            object_id,
            tuple((kind, item.id) for kind, item in locked_objects),
            (),
        )

    async def restore(
        self,
        *,
        actor_id: UUID,
        object_type: ArchiveObjectType,
        object_id: UUID,
        reason: str | None = None,
        occurred_at: datetime | None = None,
    ) -> ArchiveEvent | None:
        normalized_reason = reason.strip() if reason is not None else None
        if normalized_reason is not None and len(normalized_reason) > 2000:
            raise ValueError(
                "Причина восстановления не должна превышать 2000 символов."
            )

        await self._ensure_access(actor_id, object_type, object_id)
        target = await self._get_object(object_type, object_id)
        locked = await self._lock_archive_chain(object_type, target)
        target = next(item for kind, item in locked if kind == object_type)
        if target.deleted_at is None:
            return None

        self._ensure_parents_active(object_type, locked)
        target.deleted_at = None
        target.deleted_by = None
        event = ArchiveEvent(
            operation_id=uuid7(),
            event_type=ArchiveEventType.RESTORED,
            actor_id=actor_id,
            occurred_at=occurred_at or datetime.now(UTC),
            reason=normalized_reason,
            **{f"{object_type}_id": target.id},
        )
        await self.repository.add_events([event])
        return event

    async def get_history(
        self,
        *,
        actor_id: UUID,
        object_type: ArchiveObjectType,
        object_id: UUID,
    ) -> list[ArchiveEvent]:
        await self._ensure_access(actor_id, object_type, object_id)
        await self._get_object(object_type, object_id)
        return await self.repository.get_history(object_type, object_id)

    async def _ensure_access(
        self,
        actor_id: UUID,
        object_type: ArchiveObjectType,
        object_id: UUID,
    ) -> None:
        actor = await self.access_service.user_repository.get_by_id(actor_id)
        if actor is None or actor.role not in _ALLOWED_ROLES:
            raise ObjectAccessDeniedError
        checker = {
            "substation": self.access_service.can_access_substation,
            "connection": self.access_service.can_access_connection,
            "urza": self.access_service.can_access_urza,
        }[object_type]
        if not await checker(user_id=actor_id, **{f"{object_type}_id": object_id}):
            raise ObjectAccessDeniedError

    async def _get_object(self, object_type: ArchiveObjectType, object_id: UUID):
        item = await self.repository.get_object(object_type, object_id)
        if item is None:
            raise ObjectNotFoundError
        return item

    async def _lock_archive_chain(self, object_type: ArchiveObjectType, target):
        if object_type == "substation":
            substation = await self.repository.lock_object("substation", target.id)
            if substation is None:
                raise ObjectNotFoundError
            return [("substation", substation)]

        connection = (
            target
            if object_type == "connection"
            else await self.repository.get_object("connection", target.connection_id)
        )
        if connection is None:
            raise ObjectNotFoundError
        substation = await self.repository.lock_object(
            "substation", connection.substation_id
        )
        if substation is None:
            raise ObjectNotFoundError
        locked_connection = await self.repository.lock_object(
            "connection", connection.id
        )
        if locked_connection is None:
            raise ObjectNotFoundError
        if locked_connection.substation_id != substation.id:
            raise PermissionError("Связь объекта изменилась. Повторите операцию.")
        locked = [("substation", substation), ("connection", locked_connection)]
        if object_type == "urza":
            locked_urza = await self.repository.lock_object("urza", target.id)
            if locked_urza is None:
                raise ObjectNotFoundError
            if locked_urza.connection_id != locked_connection.id:
                raise PermissionError("Связь объекта изменилась. Повторите операцию.")
            locked.append(("urza", locked_urza))
        return locked

    async def _locked_cascade(self, object_type: ArchiveObjectType, target):
        if object_type == "urza":
            return [("urza", target)]
        if object_type == "connection":
            connections = [("connection", target)]
        else:
            connections = []
            for connection in await self.repository.get_active_connections(target.id):
                locked = await self.repository.lock_object("connection", connection.id)
                if (
                    locked is not None
                    and locked.deleted_at is None
                    and locked.substation_id == target.id
                ):
                    connections.append(("connection", locked))

        connection_ids = [item.id for _, item in connections]
        urzas = []
        for urza in await self.repository.get_active_urzas(connection_ids):
            locked = await self.repository.lock_object("urza", urza.id)
            if (
                locked is not None
                and locked.deleted_at is None
                and locked.connection_id in connection_ids
            ):
                urzas.append(("urza", locked))
        return (
            ([("substation", target)] if object_type == "substation" else [])
            + connections
            + urzas
        )

    async def _cascade_objects(self, object_type: ArchiveObjectType, target):
        if object_type == "urza":
            return [("urza", target)] if target.deleted_at is None else []
        if object_type == "connection":
            connections = [("connection", target)] if target.deleted_at is None else []
            connection_ids = [target.id] if target.deleted_at is None else []
            urzas = await self.repository.get_active_urzas(connection_ids)
            return connections + [("urza", urza) for urza in urzas]
        connections = await self.repository.get_active_connections(target.id)
        urzas = await self.repository.get_active_urzas(
            [item.id for item in connections]
        )
        return (
            [("substation", target)]
            + [("connection", item) for item in connections]
            + [("urza", item) for item in urzas]
        )

    async def _blockers(self, object_type: ArchiveObjectType, target, objects):
        urza_ids = [item.id for kind, item in objects if kind == "urza"]
        rows = await self.repository.get_blocking_processes(
            substation_id=(target.id if object_type == "substation" else None),
            urza_ids=urza_ids,
            include_inspections=object_type == "substation",
        )
        return [ArchiveBlocker(*row) for row in rows]

    @staticmethod
    def _ensure_parents_active(object_type: ArchiveObjectType, locked) -> None:
        if object_type == "substation":
            return
        substation = next(item for kind, item in locked if kind == "substation")
        if substation.deleted_at is not None:
            raise ValueError("Нельзя восстановить объект архивной подстанции.")
        if object_type == "urza":
            connection = next(item for kind, item in locked if kind == "connection")
            if connection.deleted_at is not None:
                raise ValueError("Нельзя восстановить УРЗА архивного присоединения.")
