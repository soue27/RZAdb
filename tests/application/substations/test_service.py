from decimal import Decimal

import pytest
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.substations.service import SubstationService
from app.domain.enums import HighestVoltage, OperationalCurrentType


class FakeSubstation:
    def __init__(
        self,
        substation_id,
        dispatch_name,
        highest_voltage,
        operational_current_type,
        sap_code,
        asureo_code,
        address,
        latitude,
        longitude,
    ):
        self.id = substation_id
        self.dispatch_name = dispatch_name
        self.highest_voltage = highest_voltage
        self.operational_current_type = operational_current_type
        self.sap_code = sap_code
        self.asureo_code = asureo_code
        self.address = address
        self.latitude = latitude
        self.longitude = longitude


class FakeSubstationRepository:
    def __init__(self, substation=None):
        self.substation = substation
        self.received_id = None

    async def get_by_id(self, substation_id):
        self.received_id = substation_id
        return self.substation


@pytest.mark.asyncio
async def test_get_details_returns_dto():
    substation_id = uuid7()

    substation = FakeSubstation(
        substation_id=substation_id,
        dispatch_name="ПС Тестовая",
        highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        sap_code="SAP001",
        asureo_code="ASU001",
        address="г. Пермь",
        latitude=Decimal("58.010000"),
        longitude=Decimal("56.250000"),
    )

    repository = FakeSubstationRepository(substation)
    service = SubstationService(repository)

    result = await service.get_details(substation_id)

    assert result is not None
    assert result.id == substation_id
    assert result.dispatch_name == "ПС Тестовая"
    assert result.highest_voltage == HighestVoltage.KV_110
    assert result.operational_current_type == OperationalCurrentType.PERMANENT
    assert result.sap_code == "SAP001"
    assert result.asureo_code == "ASU001"
    assert result.address == "г. Пермь"
    assert result.latitude == Decimal("58.010000")
    assert result.longitude == Decimal("56.250000")

    assert repository.received_id == substation_id


@pytest.mark.asyncio
async def test_get_details_raises_for_missing_substation():
    substation_id = uuid7()

    repository = FakeSubstationRepository(None)
    service = SubstationService(repository)

    with pytest.raises(ObjectNotFoundError):
        await service.get_details(substation_id)

    assert repository.received_id == substation_id


@pytest.mark.asyncio
async def test_get_details_maps_substation_model():
    substation_id = uuid7()

    substation = FakeSubstation(
        substation_id=substation_id,
        dispatch_name="ПС Северная",
        highest_voltage=HighestVoltage.KV_220,
        operational_current_type=OperationalCurrentType.RECTIFIED,
        sap_code=None,
        asureo_code=None,
        address=None,
        latitude=None,
        longitude=None,
    )

    repository = FakeSubstationRepository(substation)
    service = SubstationService(repository)

    result = await service.get_details(substation_id)

    assert result is not None
    assert result.id == substation.id
    assert result.dispatch_name == substation.dispatch_name
    assert result.highest_voltage == substation.highest_voltage
    assert result.operational_current_type == substation.operational_current_type
    assert result.sap_code is None
    assert result.asureo_code is None
    assert result.address is None
    assert result.latitude is None
    assert result.longitude is None