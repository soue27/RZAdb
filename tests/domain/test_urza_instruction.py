from sqlalchemy import UniqueConstraint

from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


def test_urza_instruction_model(system_user_id) -> None:
    instruction = URZAInstruction(created_by=system_user_id, updated_by=system_user_id)

    assert instruction.urza_id is None


def test_urza_instruction_version_model(system_user_id) -> None:
    version = URZAInstructionVersion(
        created_by=system_user_id, updated_by=system_user_id
    )

    assert version.urza_instruction_id is None
    assert version.version_number is None
    assert version.effective_date is None
    assert version.change_description is None
    assert version.change_justification is None
    assert version.created_by == system_user_id
    assert version.scan_file_id is None
    assert version.editable_file_id is None


def test_instruction_version_number_is_unique_per_instruction() -> None:
    constraints = URZAInstructionVersion.__table__.constraints
    assert any(
        isinstance(constraint, UniqueConstraint)
        and set(constraint.columns.keys())
        == {"urza_instruction_id", "version_number"}
        for constraint in constraints
    )
