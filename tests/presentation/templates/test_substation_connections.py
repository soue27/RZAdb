from uuid6 import uuid7

from fastapi.templating import Jinja2Templates

from app.application.connections.schemas import ConnectionListItem
from app.domain.enums import OperationalCurrentType


templates = Jinja2Templates(directory="app/presentation/templates")


def test_substation_connections_template_renders_connections():
    connections = [
        ConnectionListItem(
            id=uuid7(),
            dispatch_name="ВЛ 110 кВ Северная",
            sap_code="SAP-001",
            asureo_code="ASUREO-001",
            rdu_subordination=True,
            operational_current_type=OperationalCurrentType.PERMANENT,
        ),
        ConnectionListItem(
            id=uuid7(),
            dispatch_name="СВ 110 кВ",
            sap_code=None,
            asureo_code=None,
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.RECTIFIED,
        ),
    ]

    template = templates.get_template(
        "objects/substation_connections.html",
    )

    html = template.render(connections=connections)

    assert "ВЛ 110 кВ Северная" in html
    assert "SAP-001" in html
    assert "ASUREO-001" in html
    assert "Да" in html

    assert "СВ 110 кВ" in html
    assert "Нет" in html


def test_substation_connections_template_renders_empty_state():
    template = templates.get_template(
        "objects/substation_connections.html",
    )

    html = template.render(connections=[])

    assert "Присоединения отсутствуют." in html