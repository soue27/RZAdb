import pytest
from sqlalchemy.exc import IntegrityError
from uuid6 import uuid7

from app.application.connections.schemas import ConnectionCreate
from app.application.connections.service import (
    ConnectionNameConflictError,
    ConnectionService,
)


class FakeConnection:
    def __init__(
        self,
        connection_id,
        dispatch_name,
        sap_code,
        asureo_code,
        rdu_subordination,
    ):
        self.id = connection_id
        self.dispatch_name = dispatch_name
        self.sap_code = sap_code
        self.asureo_code = asureo_code
        self.rdu_subordination = rdu_subordination


class FakeConnectionRepository:
    def __init__(self, connections):
        self.connections = connections
        self.received_ids = None
        self.received_id = None
        self.name_exists = False
        self.added = None
        self.commit_calls = 0
        self.rollback_calls = 0

    async def exists_by_name(self, substation_id, dispatch_name):
        self.received_name = (substation_id, dispatch_name)
        return self.name_exists

    async def add(self, connection):
        connection.id = uuid7()
        self.added = connection
        return connection

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def get_by_id(self, connection_id):
        self.received_id = connection_id

        for connection in self.connections:
            if connection.id == connection_id:
                return connection

        return None

    async def get_by_substation_ids(self, substation_ids):
        self.received_ids = substation_ids
        return self.connections


@pytest.mark.asyncio
async def test_get_by_id_returns_connection_dto():
    connection_id = uuid7()

    connection = FakeConnection(
        connection_id=connection_id,
        dispatch_name="ВЛ 110 кВ Северная",
        sap_code="SAP-001",
        asureo_code="ASUREO-001",
        rdu_subordination=True,
    )

    repository = FakeConnectionRepository([connection])
    service = ConnectionService(repository)

    result = await service.get_by_id(connection_id)

    assert repository.received_id == connection_id

    assert result is not None
    assert result.id == connection_id
    assert result.dispatch_name == "ВЛ 110 кВ Северная"
    assert result.sap_code == "SAP-001"
    assert result.asureo_code == "ASUREO-001"
    assert result.rdu_subordination is True


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_connection():
    connection_id = uuid7()

    repository = FakeConnectionRepository([])
    service = ConnectionService(repository)

    result = await service.get_by_id(connection_id)

    assert result is None
    assert repository.received_id == connection_id


@pytest.mark.asyncio
async def test_get_by_substation_id_returns_connection_dtos():
    substation_id = uuid7()
    connection_id = uuid7()

    connection = FakeConnection(
        connection_id=connection_id,
        dispatch_name="ВЛ 110 кВ Северная",
        sap_code="SAP-001",
        asureo_code="ASUREO-001",
        rdu_subordination=True,
    )

    repository = FakeConnectionRepository([connection])
    service = ConnectionService(repository)

    result = await service.get_by_substation_id(substation_id)

    assert repository.received_ids == {substation_id}

    assert len(result) == 1
    assert result[0].id == connection_id
    assert result[0].dispatch_name == "ВЛ 110 кВ Северная"
    assert result[0].sap_code == "SAP-001"
    assert result[0].asureo_code == "ASUREO-001"
    assert result[0].rdu_subordination is True


@pytest.mark.asyncio
async def test_get_by_substation_id_returns_empty_list():
    substation_id = uuid7()

    repository = FakeConnectionRepository([])
    service = ConnectionService(repository)

    result = await service.get_by_substation_id(substation_id)

    assert result == []
    assert repository.received_ids == {substation_id}


@pytest.mark.asyncio
async def test_create_connection_sets_parent_and_audit_fields():
    substation_id, actor_id = uuid7(), uuid7()
    repository = FakeConnectionRepository([])
    service = ConnectionService(repository)
    result = await service.create(
        substation_id=substation_id,
        actor_id=actor_id,
        data=ConnectionCreate(
            dispatch_name="ВЛ 110 кВ", rdu_subordination=True,
            sap_code=None, asureo_code=None,
        ),
    )
    assert repository.received_name == (substation_id, "ВЛ 110 кВ")
    assert repository.added.substation_id == substation_id
    assert repository.added.created_by == actor_id
    assert repository.added.updated_by == actor_id
    assert result.id == repository.added.id
    assert result.dispatch_name == "ВЛ 110 кВ"
    assert repository.commit_calls == 0
    assert repository.rollback_calls == 0


@pytest.mark.asyncio
async def test_create_connection_rejects_duplicate_name_before_insert():
    repository = FakeConnectionRepository([])
    repository.name_exists = True
    service = ConnectionService(repository)
    with pytest.raises(ConnectionNameConflictError):
        await service.create(
            substation_id=uuid7(), actor_id=uuid7(),
            data=ConnectionCreate(dispatch_name="ВЛ", rdu_subordination=False),
        )
    assert repository.added is None


@pytest.mark.asyncio
async def test_create_connection_translates_unique_race():
    class RacingRepository(FakeConnectionRepository):
        async def add(self, connection):
            raise IntegrityError(
                "INSERT", {}, type("UniqueViolation", (), {
                    "constraint_name": "uq_connections_substation_dispatch_name",
                })(),
            )

    repository = RacingRepository([])
    service = ConnectionService(repository)
    with pytest.raises(ConnectionNameConflictError):
        await service.create(
            substation_id=uuid7(), actor_id=uuid7(),
            data=ConnectionCreate(dispatch_name="ВЛ", rdu_subordination=True),
        )
    assert repository.commit_calls == 0
    assert repository.rollback_calls == 0


@pytest.mark.asyncio
async def test_create_connection_propagates_unrelated_integrity_error():
    class UnrelatedConstraintRepository(FakeConnectionRepository):
        async def add(self, connection):
            raise IntegrityError(
                "INSERT", {}, type("UniqueViolation", (), {
                    "constraint_name": "uq_connections_sap_code",
                })(),
            )

    repository = UnrelatedConstraintRepository([])
    service = ConnectionService(repository)
    with pytest.raises(IntegrityError):
        await service.create(
            substation_id=uuid7(), actor_id=uuid7(),
            data=ConnectionCreate(dispatch_name="ВЛ", rdu_subordination=True),
        )
    assert repository.commit_calls == 0
    assert repository.rollback_calls == 0
