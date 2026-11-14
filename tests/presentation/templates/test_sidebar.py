import re
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates
from uuid6 import uuid7


templates = Jinja2Templates(directory="app/presentation/templates")


def test_enterprise_tree_labels_use_short_names():
    department = SimpleNamespace(
        id=uuid7(), type="department", full_name="Полное название ПО",
        short_name="Краткое ПО", children=[], substations=[],
    )
    branch = SimpleNamespace(
        id=uuid7(), type="branch", full_name="Полное название филиала",
        short_name="Краткий филиал", children=[department], substations=[],
    )
    holding = SimpleNamespace(
        id=uuid7(), type="holding", full_name="Полное название холдинга",
        short_name="Краткий холдинг", children=[branch], substations=[],
    )

    html = templates.get_template("components/sidebar.html").render(tree=[holding])

    labels = re.findall(r'<span class="tree-label">\s*(.*?)\s*</span>', html, re.DOTALL)

    assert labels[:3] == ["Краткий холдинг", "Краткий филиал", "Краткое ПО"]
