import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.connections.schemas import ConnectionCreate
from app.application.connections.service import ConnectionService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.objects.archive_repository import ArchiveRepository
from app.application.objects.archive_service import ArchiveBlockedError, ArchiveService
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository
from app.application.urzas.schemas import URZACreate
from app.application.urzas.service import URZAService
from app.application.users.repository import UserRepository
from app.domain.archive_event import ArchiveEvent
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    ArchiveEventType,
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    TaskStatus,
    TaskWorkType,
    URZACategory,
    URZAStatus,
    UserRole,
)
from app.domain.inspection_task import InspectionTask
from app.domain.substation import Substation
from app.domain.task import Task
from app.domain.urza import URZA
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


def _archive_service(session: AsyncSession) -> ArchiveService:
    users = UserRepository(session)
    substations = SubstationRepository(session)
    enterprises = EnterpriseRepository(session)
    connections = ConnectionRepository(session)
    urzas = URZARepository(session)
    access = AccessService(users, substations, enterprises, connections, urzas)
    return ArchiveService(ArchiveRepository(session), access)


async def _seed_graph(session: AsyncSession, system_user_id):
    department = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name=f"Archive test {uuid4()}",
        short_name=f"Archive {uuid4()}",
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    actor = User(
        id=uuid4(),
        full_name="Archive test manager",
        role=UserRole.MANAGER,
        email=f"{uuid4()}@example.test",
        password_hash="integration-test-only",
        enterprise_id=department.id,
        access_category=AccessCategory.IV,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    substation = Substation(
        id=uuid4(),
        enterprise_id=department.id,
        highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        dispatch_name=f"ПС archive {uuid4()}",
        created_by=actor.id,
        updated_by=actor.id,
    )
    connection = Connection(
        id=uuid4(),
        substation_id=substation.id,
        dispatch_name=f"Линия {uuid4()}",
        rdu_subordination=False,
        created_by=actor.id,
        updated_by=actor.id,
    )
    urza = URZA(
        id=uuid4(),
        connection_id=connection.id,
        dispatch_name=f"УРЗА {uuid4()}",
        rdu_subordination=False,
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.III,
        room_category=RoomCategory.III,
        complexity=False,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(department)
    await session.flush()
    session.add(actor)
    await session.flush()
    session.add_all([substation, connection, urza])
    await session.flush()
    return {
        "department_id": department.id,
        "actor_id": actor.id,
        "substation_id": substation.id,
        "connection_id": connection.id,
        "urza_id": urza.id,
    }


@pytest_asyncio.fixture
async def committed_archive_graph(system_user_id):
    """Committed rows for multi-session lock tests; cleanup is ID-scoped."""
    ids = None
    async with async_session_factory() as session:
        ids = await _seed_graph(session, system_user_id)
        await session.commit()

    try:
        yield ids
    finally:
        async with async_session_factory() as session:
            connection_ids = select(Connection.id).where(
                Connection.substation_id == ids["substation_id"]
            )
            urza_ids = select(URZA.id).where(URZA.connection_id.in_(connection_ids))
            await session.execute(
                delete(ArchiveEvent).where(
                    (ArchiveEvent.substation_id == ids["substation_id"])
                    | ArchiveEvent.connection_id.in_(connection_ids)
                    | ArchiveEvent.urza_id.in_(urza_ids)
                    | (ArchiveEvent.actor_id == ids["actor_id"])
                )
            )
            await session.execute(
                delete(Task).where(
                    (Task.substation_id == ids["substation_id"])
                    | Task.urza_id.in_(urza_ids)
                )
            )
            await session.execute(
                delete(InspectionTask).where(
                    InspectionTask.substation_id == ids["substation_id"]
                )
            )
            await session.execute(delete(URZA).where(URZA.id.in_(urza_ids)))
            await session.execute(
                delete(Connection).where(Connection.id.in_(connection_ids))
            )
            await session.execute(
                delete(Substation).where(Substation.id == ids["substation_id"])
            )
            await session.execute(delete(User).where(User.id == ids["actor_id"]))
            await session.execute(
                delete(Enterprise).where(Enterprise.id == ids["department_id"])
            )
            await session.commit()


@pytest.mark.asyncio
async def test_substation_archive_cascades_and_writes_shared_operation_events(
    db_session, system_user_id
):
    graph = await _seed_graph(db_session, system_user_id)
    service = _archive_service(db_session)

    await service.archive(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
        reason="Проверка каскада",
    )

    for model, object_id in (
        (Substation, graph["substation_id"]),
        (Connection, graph["connection_id"]),
        (URZA, graph["urza_id"]),
    ):
        obj = await db_session.get(model, object_id)
        assert obj is not None and obj.deleted_at is not None

    events = list(
        (
            await db_session.scalars(
                select(ArchiveEvent).where(ArchiveEvent.actor_id == graph["actor_id"])
            )
        ).all()
    )
    assert len(events) == 3
    assert {event.event_type for event in events} == {ArchiveEventType.ARCHIVED}
    assert len({event.operation_id for event in events}) == 1
    assert {event.reason for event in events} == {"Проверка каскада"}


@pytest.mark.asyncio
async def test_blocking_task_rejects_archive_without_partial_changes_or_events(
    db_session, system_user_id
):
    graph = await _seed_graph(db_session, system_user_id)
    db_session.add(
        Task(
            substation_id=graph["substation_id"],
            work_type=TaskWorkType.INSTRUCTION,
            status=TaskStatus.IN_PROGRESS,
            created_by=graph["actor_id"],
            updated_by=graph["actor_id"],
        )
    )
    await db_session.flush()

    with pytest.raises(ArchiveBlockedError):
        await _archive_service(db_session).archive(
            actor_id=graph["actor_id"],
            object_type="substation",
            object_id=graph["substation_id"],
            reason="Есть активное задание",
        )

    assert (await db_session.get(Substation, graph["substation_id"])).deleted_at is None
    assert (await db_session.get(Connection, graph["connection_id"])).deleted_at is None
    assert (await db_session.get(URZA, graph["urza_id"])).deleted_at is None
    assert (
        await db_session.scalar(
            select(ArchiveEvent.id).where(ArchiveEvent.actor_id == graph["actor_id"])
        )
        is None
    )


@pytest.mark.asyncio
async def test_blocking_inspection_rejects_substation_archive_without_events(
    db_session, system_user_id
):
    graph = await _seed_graph(db_session, system_user_id)
    db_session.add(
        InspectionTask(
            substation_id=graph["substation_id"],
            status=TaskStatus.ASSIGNED,
            deadline_at=datetime.now(UTC),
            created_by=graph["actor_id"],
            updated_by=graph["actor_id"],
        )
    )
    await db_session.flush()

    with pytest.raises(ArchiveBlockedError):
        await _archive_service(db_session).archive(
            actor_id=graph["actor_id"],
            object_type="substation",
            object_id=graph["substation_id"],
            reason="Есть активный осмотр",
        )

    assert (await db_session.get(Substation, graph["substation_id"])).deleted_at is None
    assert (await db_session.get(Connection, graph["connection_id"])).deleted_at is None
    assert (await db_session.get(URZA, graph["urza_id"])).deleted_at is None
    assert not (
        await db_session.scalars(
            select(ArchiveEvent).where(ArchiveEvent.actor_id == graph["actor_id"])
        )
    ).all()


@pytest.mark.asyncio
async def test_restore_changes_only_selected_object_and_rejects_archived_parent(
    db_session, system_user_id
):
    graph = await _seed_graph(db_session, system_user_id)
    service = _archive_service(db_session)
    await service.archive(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
        reason="Восстановление по тесту",
    )

    with pytest.raises(ValueError, match="архивной подстанции"):
        await service.restore(
            actor_id=graph["actor_id"],
            object_type="connection",
            object_id=graph["connection_id"],
        )

    await service.restore(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
    )
    assert (await db_session.get(Substation, graph["substation_id"])).deleted_at is None
    assert (
        await db_session.get(Connection, graph["connection_id"])
    ).deleted_at is not None
    assert (await db_session.get(URZA, graph["urza_id"])).deleted_at is not None


@pytest.mark.asyncio
async def test_archive_and_restore_noops_do_not_append_events(
    db_session, system_user_id
):
    graph = await _seed_graph(db_session, system_user_id)
    service = _archive_service(db_session)
    await service.archive(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
        reason="Первичное архивирование",
    )
    initial_event_ids = set(
        (
            await db_session.scalars(
                select(ArchiveEvent.id).where(
                    ArchiveEvent.actor_id == graph["actor_id"]
                )
            )
        ).all()
    )
    await service.archive(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
        reason="Повторный запрос",
    )
    await service.restore(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
    )
    await service.restore(
        actor_id=graph["actor_id"],
        object_type="substation",
        object_id=graph["substation_id"],
    )
    final_event_ids = set(
        (
            await db_session.scalars(
                select(ArchiveEvent.id).where(
                    ArchiveEvent.actor_id == graph["actor_id"]
                )
            )
        ).all()
    )
    assert len(final_event_ids) == len(initial_event_ids) + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_type", ["substation", "connection"])
async def test_concurrent_child_creation_waits_for_archive_and_is_rejected(
    committed_archive_graph, owner_type
):
    graph = committed_archive_graph

    async with async_session_factory() as archive_session:
        await _archive_service(archive_session).archive(
            actor_id=graph["actor_id"],
            object_type=owner_type,
            object_id=graph[f"{owner_type}_id"],
            reason="Конкурентный тест",
        )

        creation_started = asyncio.Event()

        async def create_child():
            async with async_session_factory() as create_session:
                creation_started.set()
                if owner_type == "substation":
                    return await ConnectionService(
                        ConnectionRepository(create_session)
                    ).create(
                        substation_id=graph["substation_id"],
                        actor_id=graph["actor_id"],
                        data=ConnectionCreate(
                            dispatch_name=f"Новое присоединение {uuid4()}",
                            rdu_subordination=False,
                        ),
                    )
                return await URZAService(URZARepository(create_session)).create(
                    connection_id=graph["connection_id"],
                    actor_id=graph["actor_id"],
                    data=URZACreate(
                        dispatch_name=f"Новая УРЗА {uuid4()}",
                        rdu_subordination=False,
                        commissioning_date=date(2020, 1, 1),
                        status=URZAStatus.IN_OPERATION,
                        element_base=ElementBase.MICROPROCESSOR,
                        category=URZACategory.III,
                        room_category=RoomCategory.III,
                        complexity=False,
                    ),
                )

        creation = asyncio.create_task(create_child())
        try:
            await asyncio.wait_for(creation_started.wait(), timeout=5)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(creation), timeout=0.2)
            await archive_session.commit()
            from app.application.objects.exceptions import ObjectNotFoundError

            with pytest.raises(ObjectNotFoundError):
                await asyncio.wait_for(creation, timeout=5)
        finally:
            if not creation.done():
                creation.cancel()
                await asyncio.gather(creation, return_exceptions=True)
