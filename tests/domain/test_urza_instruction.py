from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


def test_urza_instruction_model() -> None:
    instruction = URZAInstruction()

    assert instruction.urza_id is None


def test_urza_instruction_version_model() -> None:
    version = URZAInstructionVersion()

    assert version.urza_instruction_id is None
    assert version.version_number is None
    assert version.effective_date is None
    assert version.change_description is None
    assert version.change_justification is None
    assert version.created_by is None
    assert version.scan_file_id is None
    assert version.editable_file_id is None