from decimal import Decimal

import pytest
from pydantic import ValidationError

from uuid6 import uuid7

from app.application.substations.schemas import SubstationDetails, SubstationUpdate
from app.domain.enums import HighestVoltage, OperationalCurrentType


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
        operational_current_type=OperationalCurrentType.PERMANENT,
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
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    assert substation.sap_code is None
    assert substation.asureo_code is None
    assert substation.address is None
    assert substation.latitude is None
    assert substation.longitude is None


def test_operational_current_type_labels() -> None:
    assert OperationalCurrentType.PERMANENT.label == "Постоянный ток"
    assert OperationalCurrentType.RECTIFIED.label == "Выпрямленный ток"
    assert OperationalCurrentType.ALTERNATING.label == "Переменный ток"


def test_substation_update_validates_and_cleans_optional_fields() -> None:
    result = SubstationUpdate(
        dispatch_name="ПС Тестовая", highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        sap_code="", asureo_code="  ", address="", latitude="90", longitude="-180",
    )
    assert result.sap_code is result.asureo_code is result.address is None
    assert result.latitude == Decimal("90")
    assert result.longitude == Decimal("-180")


@pytest.mark.parametrize("field,value", [("dispatch_name", "  "), ("latitude", "90.01"), ("latitude", "-90.01"), ("longitude", "180.01"), ("longitude", "-180.01")])
def test_substation_update_rejects_invalid_values(field, value) -> None:
    data = {
        "dispatch_name": "ПС", "highest_voltage": HighestVoltage.KV_110,
        "operational_current_type": OperationalCurrentType.PERMANENT,
        "latitude": None, "longitude": None,
    }
    data[field] = value
    with pytest.raises(ValidationError):
        SubstationUpdate(**data)
