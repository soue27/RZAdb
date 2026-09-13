from app.domain.program import Program


def test_program_model() -> None:
    program = Program()

    assert program.__tablename__ == "programs"

    assert program.__table__.c.urza_id.nullable is False
    assert program.__table__.c.program_type.nullable is False
    assert program.__table__.c.program_number.nullable is False
    assert program.__table__.c.scan_file_id.nullable is False
    assert program.__table__.c.editable_file_id.nullable is True
    assert program.__table__.c.task_id.nullable is True

    assert program.__table__.c.id.primary_key is True
    assert program.__table__.c.created_at.nullable is False
    assert program.__table__.c.updated_at.nullable is False
    assert program.__table__.c.deleted_at.nullable is True
    assert program.__table__.c.deleted_by.nullable is True


from app.domain.enums import ProgramType


def test_program_type() -> None:
    assert ProgramType.COMMISSIONING.value == "commissioning"
    assert ProgramType.DECOMMISSIONING.value == "decommissioning"
    assert ProgramType.WORK.value == "work"