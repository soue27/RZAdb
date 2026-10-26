from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates
from uuid6 import uuid7

from app.application.substations.schemas import SubstationDetails
from app.domain.enums import DocumentStatus, HighestVoltage, OperationalCurrentType

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

    html = template.render(substation=substation, can_create_connection=True)

    assert "ПС Центральная" in html
    assert "220 кВ" in html
    assert "SAP-220" in html
    assert "ASUREO-220" in html
    assert "г. Екатеринбург" in html
    assert "56.838900" in html
    assert "60.605700" in html
    expected_tabs = {
        "details": (
            "Основные сведения",
            f"/objects/substation/{substation.id}/details",
        ),
        "inspections": (
            "Осмотры",
            f"/objects/substation/{substation.id}/inspections",
        ),
        "instructions": (
            "Инструкции",
            f"/objects/substation/{substation.id}/instructions",
        ),
        "selectivity-schemes": (
            "Схемы селективности",
            f"/objects/substation/{substation.id}/selectivity-schemes",
        ),
    }
    assert html.count("data-rzadb-tab\n") == len(expected_tabs)
    for tab_name, (label, url) in expected_tabs.items():
        tab_marker = f'data-tab="{tab_name}"'
        tab_start = html.rfind("<button", 0, html.index(tab_marker))
        tab_end = html.index("</button>", html.index(tab_marker))
        tab_html = html[tab_start:tab_end]
        assert label in tab_html
        assert f'hx-get="{url}"' in tab_html
        assert 'hx-target="#substation-tab-content"' in tab_html
        assert 'hx-swap="innerHTML"' in tab_html

    assert 'id="substation-tab-content"' in html
    assert "Присоединения" not in html
    assert f'hx-get="/objects/substation/{substation.id}/connections"' not in html
    assert 'data-tab="connections"' not in html
    assert "Изменить" not in html
    assert "Добавить присоединение" in html
    assert f"/objects/substation/{substation.id}/connections/new" in html
    assert 'hx-target="#object-content"' in html


def test_connection_creation_button_hidden_for_other_roles():
    substation = SubstationDetails(
        id=uuid7(), dispatch_name="ПС", highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        sap_code=None, asureo_code=None, address=None, latitude=None, longitude=None,
    )
    html = templates.get_template("objects/substation.html").render(
        substation=substation, can_create_connection=False,
    )
    assert "Добавить присоединение" not in html


def test_substation_edit_button_is_rendered_only_when_allowed():
    substation = SubstationDetails(
        id=uuid7(), dispatch_name="ПС", highest_voltage=HighestVoltage.KV_110,
        operational_current_type=OperationalCurrentType.PERMANENT,
        sap_code=None, asureo_code=None, address=None, latitude=None, longitude=None,
    )
    template = templates.get_template("objects/substation_details.html")
    editable_html = template.render(substation=substation, can_edit=True)
    read_only_html = template.render(substation=substation, can_edit=False)
    assert "Изменить" in editable_html
    assert "Изменить" not in read_only_html
    assert editable_html.index("Координаты") < editable_html.index("Изменить")
    assert editable_html.index("</dl>") < editable_html.index("Изменить")


def test_substation_document_forms_support_upload_and_preserve_text_values():
    template = templates.get_template("objects/substation_document_form.html")
    substation_id = uuid7()
    html = template.render(
        substation_id=substation_id,
        document_type="scheme",
        new_version=True,
        task_id=uuid7(),
        values={"effective_date": "2026-10-15", "number": "С-110", "name": "Схема"},
        error_message="Проверьте данные",
    )
    assert "enctype=\"multipart/form-data\"" in html
    assert "Проверьте данные" in html
    assert 'value="С-110"' in html
    assert 'value="Схема"' in html
    assert 'name="task_id"' in html
    assert f"hx-target=\"#substation-tab-content\"" in html


def test_substation_instruction_actions_and_task_button_are_gated():
    template = templates.get_template("objects/substation_instructions.html")
    version = SimpleNamespace(
        id=uuid7(), version_number=1, status=DocumentStatus.DRAFT,
        effective_date=date(2026, 10, 15),
        change_description=None, change_justification=None,
        created_by_full_name="Инженер", scan_file_id=uuid7(),
        scan_file_name="scan.pdf", editable_file_id=None,
        editable_file_name=None,
    )
    context = {
        "selected_version": version, "versions": [version],
        "substation_id": uuid7(), "document_actions": {"submit"},
        "can_issue_task": False, "can_create_document": True,
        "instruction": SimpleNamespace(),
    }
    html = template.render(**context)
    assert "Отправить на согласование" in html
    assert "Выдать задание" not in html

    context["can_issue_task"] = True
    html = template.render(**context)
    assert "Выдать задание" in html


def test_substation_details_fragment_preserves_tab_container():
    template = templates.get_template(
        "objects/substation_details_fragment.html",
    )
    html = template.render(
        substation=SimpleNamespace(
            id=uuid7(),
            dispatch_name="ПС Центральная",
            highest_voltage=HighestVoltage.KV_110,
            operational_current_type=OperationalCurrentType.PERMANENT,
            sap_code=None,
            asureo_code=None,
            address=None,
            latitude=None,
            longitude=None,
        ),
        can_edit=False,
    )

    assert html.count('id="substation-tab-content"') == 1
    assert "ПС Центральная" in html
