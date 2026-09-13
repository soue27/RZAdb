
from sqlalchemy import inspect

from app.domain.otd import OTDVersion


def test_otd_version_has_optional_task_link() -> None:
    mapper = inspect(OTDVersion)

    task_id = mapper.columns["task_id"]

    assert task_id.nullable is True
    assert task_id.foreign_keys

    foreign_key = next(iter(task_id.foreign_keys))

    assert foreign_key.target_fullname == "tasks.id"
