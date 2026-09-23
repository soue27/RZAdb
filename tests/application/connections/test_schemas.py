from uuid6 import uuid7

from app.application.connections.schemas import ConnectionListItem
from app.domain.enums import OperationalCurrentType


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