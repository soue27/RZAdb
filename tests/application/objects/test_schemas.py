from uuid6 import uuid7

from app.application.objects.schemas import SelectedObject


def test_selected_object_schema() -> None:
    object_id = uuid7()

    selected_object = SelectedObject(
        object_type="substation",
        id=object_id,
        name="ПС Свердловская",
    )

    assert selected_object.object_type == "substation"
    assert selected_object.id == object_id
    assert selected_object.name == "ПС Свердловская"