from uuid import uuid4

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/presentation/templates")


def test_active_archive_actions_offer_preview_and_history_only_to_allowed_users():
    object_id = uuid4()
    template = templates.get_template("objects/archive_actions.html")

    allowed = template.render(
        can_manage_archive=True,
        is_archived=False,
        archive_object_type="substation",
        archive_object_id=object_id,
    )
    denied = template.render(
        can_manage_archive=False,
        is_archived=False,
        archive_object_type="substation",
        archive_object_id=object_id,
    )

    assert "В архив" in allowed
    assert f"/objects/substation/{object_id}/archive/preview" in allowed
    assert f"/objects/substation/{object_id}/archive/history" in allowed
    assert "Восстановить" not in allowed
    assert "archive-preview-modal" in allowed
    assert "В архив" not in denied
    assert "История архива" not in denied


def test_archived_archive_actions_offer_single_object_restore_and_history():
    object_id = uuid4()
    html = templates.get_template("objects/archive_actions.html").render(
        can_manage_archive=True,
        is_archived=True,
        archive_object_type="urza",
        archive_object_id=object_id,
    )

    assert "В архиве" in html
    assert "Восстановить" in html
    assert f"/objects/urza/{object_id}/restore" in html
    assert "Причина восстановления" in html
    assert "необязательно" in html
    assert "дочерние объекты останутся в архиве" in html
    assert f"/objects/urza/{object_id}/archive/history" in html
    assert "archive-preview-modal" not in html

    read_only = templates.get_template("objects/archive_actions.html").render(
        can_manage_archive=False,
        is_archived=True,
        archive_object_type="urza",
        archive_object_id=object_id,
    )
    assert "В архиве" in read_only
    assert "Восстановить" not in read_only
    assert "История архива" not in read_only


def test_archive_preview_requires_reason_and_posts_no_child_ids():
    object_id = uuid4()
    html = templates.get_template("objects/archive_preview.html").render(
        object_type="connection",
        object_id=object_id,
        objects=[
            {"type": "connection", "label": "Присоединение", "id": object_id},
            {"type": "urza", "label": "УРЗА", "id": uuid4()},
        ],
        blockers=[],
    )

    assert f'action="/objects/connection/{object_id}/archive"' in html
    assert f'hx-post="/objects/connection/{object_id}/archive"' in html
    assert 'name="reason"' in html
    assert 'maxlength="2000"' in html
    assert "required" in html
    assert "connection_ids" not in html
    assert "Подтвердить архивирование" in html
