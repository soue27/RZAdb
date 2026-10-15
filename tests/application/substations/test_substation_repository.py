from uuid import uuid4

import pytest

from app.application.substations.repository import SubstationRepository
from app.domain.enums import HighestVoltage
from app.domain.substation import Substation


class FakeSession:
    def __init__(self) -> None:
        self.substations = {}
        self.added = None
        self.flushed = False

    def add(self, entity):
        self.added = entity

    async def flush(self):
        self.flushed = True

    async def get(self, model, object_id):
        return self.substations.get(object_id)


@pytest.mark.asyncio
async def test_get_by_id_returns_substation() -> None:
    session = FakeSession()
    repository = SubstationRepository(session)

    substation = Substation(
        id=uuid4(),
        enterprise_id=uuid4(),
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        created_by=uuid4(),
        updated_by=uuid4(),
    )

    session.substations[substation.id] = substation

    result = await repository.get_by_id(substation.id)

    assert result is substation


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_substation() -> None:
    session = FakeSession()
    repository = SubstationRepository(session)

    result = await repository.get_by_id(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_save_adds_and_flushes_substation() -> None:
    session = FakeSession()
    repository = SubstationRepository(session)
    substation = Substation(id=uuid4(), enterprise_id=uuid4(),
        highest_voltage=HighestVoltage.KV_110, dispatch_name="ПС Тестовая",
        created_by=uuid4(), updated_by=uuid4())
    assert await repository.save(substation) is substation
    assert session.added is substation
    assert session.flushed
