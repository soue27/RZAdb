from fastapi.templating import Jinja2Templates
from uuid6 import uuid7

templates = Jinja2Templates(directory="app/presentation/templates")


def test_connection_form_renders_parent_and_preserves_values():
    substation_id = uuid7()
    html = templates.get_template("objects/connection_form.html").render(
        substation_id=substation_id,
        form_values={
            "dispatch_name": "ВЛ 110 кВ",
            "rdu_subordination": "false",
            "sap_code": "SAP-1",
            "asureo_code": "ASUREO-1",
        },
        error_message="Ошибка формы",
    )
    assert f"/objects/substation/{substation_id}/connections" in html
    assert 'name="dispatch_name"' in html
    assert 'name="rdu_subordination"' in html
    assert 'value="ВЛ 110 кВ"' in html
    assert 'value="false" selected' in html
    assert 'value="SAP-1"' in html
    assert 'value="ASUREO-1"' in html
    assert "Ошибка формы" in html
    assert "event.detail.xhr.status === 422" in html


def test_connection_page_wraps_content_with_object_container():
    html = templates.get_template("objects/connection_page.html").render(
        content_template="objects/connection.html",
        page_title="Присоединение",
        connection=type("Connection", (), {
            "dispatch_name": "ВЛ", "sap_code": None,
            "asureo_code": None, "rdu_subordination": False,
        })(),
        tree=[],
        current_user=None,
    )
    assert 'id="object-content"' in html
    assert "Присоединение" in html
    assert "ВЛ" in html
