from decimal import Decimal

from uuid6 import uuid7

from app.application.substations.schemas import SubstationDetails
from app.domain.enums import HighestVoltage


def test_substation_details_schema() -> None:
    substation_id = uuid7()

    substation = SubstationDetails(
        id=substation_id,
        dispatch_name="ПС Свердловская",
        highest_voltage=HighestVoltage.KV_110,
        sap_code="SAP-001",
        asureo_code="ASUREO-001",
        address="г. Екатеринбург, ул. Энергетиков, 1",
        latitude=Decimal("56.838900"),
        longitude=Decimal("60.605700"),
    )

    assert substation.id == substation_id
    assert substation.dispatch_name == "ПС Свердловская"
    assert substation.highest_voltage == HighestVoltage.KV_110
    assert substation.sap_code == "SAP-001"
    assert substation.asureo_code == "ASUREO-001"
    assert substation.address == "г. Екатеринбург, ул. Энергетиков, 1"
    assert substation.latitude == Decimal("56.838900")
    assert substation.longitude == Decimal("60.605700")


def test_substation_details_allows_optional_fields_to_be_none() -> None:
    substation = SubstationDetails(
        id=uuid7(),
        dispatch_name="ПС Свердловская",
        highest_voltage=HighestVoltage.KV_110,
        sap_code=None,
        asureo_code=None,
        address=None,
        latitude=None,
        longitude=None,
    )

    assert substation.sap_code is None
    assert substation.asureo_code is None
    assert substation.address is None
    assert substation.latitude is None
    assert substation.longitude is None