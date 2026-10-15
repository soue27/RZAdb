import pytest
from pydantic import ValidationError
from uuid6 import uuid7

from app.application.connections.schemas import ConnectionCreate, ConnectionListItem


def test_connection_list_item_contains_all_fields():
    connection_id = uuid7()

    result = ConnectionListItem(
        id=connection_id,
        dispatch_name="ВЛ 110 кВ Северная",
        sap_code="SAP-001",
        asureo_code="ASUREO-001",
        rdu_subordination=True,
    )

    assert result.id == connection_id
    assert result.dispatch_name == "ВЛ 110 кВ Северная"
    assert result.sap_code == "SAP-001"
    assert result.asureo_code == "ASUREO-001"
    assert result.rdu_subordination is True


def test_connection_list_item_allows_optional_codes():
    result = ConnectionListItem(
        id=uuid7(),
        dispatch_name="СВ 110 кВ",
        sap_code=None,
        asureo_code=None,
        rdu_subordination=False,
    )

    assert result.sap_code is None
    assert result.asureo_code is None


def test_connection_create_normalizes_name_codes_and_boolean():
    result = ConnectionCreate(
        dispatch_name="  ВЛ 110 кВ  ",
        rdu_subordination="false",
        sap_code="  ",
        asureo_code="ASU-01",
    )
    assert result.dispatch_name == "ВЛ 110 кВ"
    assert result.rdu_subordination is False
    assert result.sap_code is None
    assert result.asureo_code == "ASU-01"


@pytest.mark.parametrize(
    "payload",
    [
        {"rdu_subordination": True},
        {"dispatch_name": " ", "rdu_subordination": True},
        {"dispatch_name": "x" * 256, "rdu_subordination": True},
        {"dispatch_name": "ВЛ", "rdu_subordination": "unknown"},
        {"dispatch_name": "ВЛ", "rdu_subordination": True, "sap_code": "x" * 65},
        {"dispatch_name": "ВЛ", "rdu_subordination": True, "asureo_code": "x" * 65},
    ],
)
def test_connection_create_rejects_invalid_fields(payload):
    with pytest.raises(ValidationError):
        ConnectionCreate(**payload)
