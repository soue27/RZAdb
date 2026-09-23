from decimal import Decimal

from fastapi.templating import Jinja2Templates
from uuid6 import uuid7

from app.application.substations.schemas import SubstationDetails
from app.domain.enums import HighestVoltage, OperationalCurrentType

templates = Jinja2Templates(directory="app/presentation/templates")


def test_substation_template_renders_details():
    substation = SubstationDetails(
        id=uuid7(),
        dispatch_name="ПС Центральная",
        highest_voltage=HighestVoltage.KV_220,
        sap_code="SAP-220",
        asureo_code="ASUREO-220",
        address="г. Екатеринбург",
        latitude=Decimal("56.838900"),
        longitude=Decimal("60.605700"),
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    template = templates.get_template("objects/substation.html")

    html = template.render(substation=substation)

    assert "ПС Центральная" in html
    assert "220 кВ" in html
    assert "SAP-220" in html
    assert "ASUREO-220" in html
    assert "г. Екатеринбург" in html
    assert "56.838900" in html
    assert "60.605700" in html
    assert "Основные сведения" in html
    assert "Осмотры" in html
    assert "Инструкции" in html
    assert "Схемы селективности" in html
    assert "Изменить" in html