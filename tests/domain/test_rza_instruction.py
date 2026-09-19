from app.domain.rza_instruction import RZAInstruction, RZAInstructionVersion


def test_rza_instruction_model() -> None:
    instruction = RZAInstruction()

    assert instruction.substation_id is None


def test_rza_instruction_version_model() -> None:
    version = RZAInstructionVersion()

    assert version.rza_instruction_id is None
    assert version.version_number is None
    assert version.effective_date is None
    assert version.change_description is None
    assert version.change_justification is None
    assert version.created_by is None
    assert version.scan_file_id is None
    assert version.editable_file_id is None