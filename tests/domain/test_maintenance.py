from app.domain.maintenance import TORecord


def test_to_record_model() -> None:
    record = TORecord()

    assert record.__tablename__ == "to_records"

    assert record.__table__.c.urza_id.nullable is False
    assert record.__table__.c.historical_data.nullable is True
    assert record.__table__.c.maintenance_date.nullable is False
    assert record.__table__.c.maintenance_type.nullable is False
    assert record.__table__.c.detected_deviations.nullable is False
    assert record.__table__.c.measures_taken.nullable is False
    assert record.__table__.c.created_by.nullable is False
    assert record.__table__.c.scan_protocol_id.nullable is True
    assert record.__table__.c.editable_protocol_id.nullable is True
    assert record.__table__.c.signed_form_file_id.nullable is False
    assert record.__table__.c.task_id.nullable is True