from uuid6 import uuid7

import pytest

from app.application.objects.resolver import ObjectResolver
from app.domain.connection import Connection
from app.domain.substation import Substation
from app.domain.urza import URZA


class FakeSubstationRepository:
    def __init__(self, substation: Substation | None) -> None:
        self.substation = substation

    async def get_by_id(self, object_id):
        if self.substation is not None and self.substation.id == object_id:
            return self.substation

        return None


class FakeConnectionRepository:
    def __init__(self, connection: Connection | None) -> None:
        self.connection = connection

    async def get_by_id(self, object_id):
        if self.connection is not None and self.connection.id == object_id:
            return self.connection

        return None


class FakeURZARepository:
    def __init__(self, urza: URZA | None) -> None:
        self.urza = urza

    async def get_by_id(self, object_id):
        if self.urza is not None and self.urza.id == object_id:
            return self.urza

        return None


def make_resolver(
    *,
    substation: Substation | None = None,
    connection: Connection | None = None,
    urza: URZA | None = None,
) -> ObjectResolver:
    return ObjectResolver(
        substation_repository=FakeSubstationRepository(substation),
        connection_repository=FakeConnectionRepository(connection),
        urza_repository=FakeURZARepository(urza),
    )


@pytest.mark.asyncio
async def test_resolves_substation() -> None:
    substation = Substation(
        id=uuid7(),
        enterprise_id=uuid7(),
        dispatch_name="ПС Свердловская",
        highest_voltage="110",
    )

    resolver = make_resolver(substation=substation)

    result = await resolver.resolve("substation", substation.id)

    assert result is not None
    assert result.object_type == "substation"
    assert result.id == substation.id
    assert result.name == "ПС Свердловская"


@pytest.mark.asyncio
async def test_resolves_connection() -> None:
    connection = Connection(
        id=uuid7(),
        substation_id=uuid7(),
        dispatch_name="ВЛ 110 кВ Свердловская",
        rdu_subordination=False,
    )

    resolver = make_resolver(connection=connection)

    result = await resolver.resolve("connection", connection.id)

    assert result is not None
    assert result.object_type == "connection"
    assert result.id == connection.id
    assert result.name == "ВЛ 110 кВ Свердловская"


@pytest.mark.asyncio
async def test_resolves_urza() -> None:
    urza = URZA(
        id=uuid7(),
        connection_id=uuid7(),
        dispatch_name="ДЗЛ-110",
        rdu_subordination=False,
        commissioning_date="2026-01-01",
        status="in_operation",
        element_base="microprocessor",
        category="II",
        room_category="I",
        complexity=False,
    )

    resolver = make_resolver(urza=urza)

    result = await resolver.resolve("urza", urza.id)

    assert result is not None
    assert result.object_type == "urza"
    assert result.id == urza.id
    assert result.name == "ДЗЛ-110"


@pytest.mark.asyncio
async def test_returns_none_for_unknown_object_type() -> None:
    resolver = make_resolver()

    result = await resolver.resolve("unknown", uuid7())

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_object_does_not_exist() -> None:
    resolver = make_resolver()

    result = await resolver.resolve("substation", uuid7())

    assert result is None