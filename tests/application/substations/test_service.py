from decimal import Decimal
from uuid6 import uuid7

import pytest

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.substations.service import SubstationService
from app.domain.enums import HighestVoltage
from app.domain.substation import Substation


class FakeSubstation:
    def __init__(self) -> None:
        self.id = uuid7()
        self.dispatch_name = "ПС Северная"
        self.highest_voltage = HighestVoltage.KV_110
        self.sap_code = "SAP-001"
        self.asureo_code = "ASUREO-001"
        self.address = "г. Екатеринбург"
        self.latitude = Decimal("56.838900")
        self.longitude = Decimal("60.605700")


class FakeSubstationRepository:
    def __init__(self, substation=None) -> None:
        self.substation = substation

    async def get_by_id(self, substation_id):
        return self.substation


@pytest.mark.asyncio
async def test_get_details_returns_dto():
    substation = FakeSubstation()
    repository = FakeSubstationRepository(substation)
    service = SubstationService(repository)

    result = await service.get_details(substation.id)

    assert result.id == substation.id
    assert result.dispatch_name == "ПС Северная"
    assert result.highest_voltage == HighestVoltage.KV_110
    assert result.sap_code == "SAP-001"
    assert result.asureo_code == "ASUREO-001"
    assert result.address == "г. Екатеринбург"
    assert result.latitude == Decimal("56.838900")
    assert result.longitude == Decimal("60.605700")


@pytest.mark.asyncio
async def test_get_details_raises_when_substation_not_found():
    repository = FakeSubstationRepository()
    service = SubstationService(repository)

    with pytest.raises(ObjectNotFoundError):
        await service.get_details(uuid7())


@pytest.mark.asyncio
async def test_get_details_maps_substation_model():
    substation_id = uuid7()
    substation = Substation(
        id=substation_id,
        enterprise_id=uuid7(),
        dispatch_name="ПС Центральная",
        highest_voltage=HighestVoltage.KV_220,
        sap_code="SAP-220",
        asureo_code="ASUREO-220",
        address="г. Екатеринбург",
        latitude=Decimal("56.838900"),
        longitude=Decimal("60.605700"),
    )

    repository = FakeSubstationRepository(substation)
    service = SubstationService(repository)

    result = await service.get_details(substation.id)

    assert result.id == substation.id
    assert result.dispatch_name == "ПС Центральная"
    assert result.highest_voltage == HighestVoltage.KV_220
    assert result.sap_code == "SAP-220"
    assert result.asureo_code == "ASUREO-220"
    assert result.address == "г. Екатеринбург"
    assert result.latitude == Decimal("56.838900")
    assert result.longitude == Decimal("60.605700")