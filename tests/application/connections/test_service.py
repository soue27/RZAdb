from uuid6 import uuid7

import pytest

from app.application.connections.service import ConnectionService
from app.domain.enums import OperationalCurrentType


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