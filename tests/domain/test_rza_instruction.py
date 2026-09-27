from app.domain.rza_instruction import RZAInstruction, RZAInstructionVersion


def test_rza_instruction_model(system_user_id) -> None:
    instruction = RZAInstruction(created_by=system_user_id, updated_by=system_user_id)

    assert instruction.substation_id is None


def test_rza_instruction_version_model(system_user_id) -> None:
    version = RZAInstructionVersion(
        created_by=system_user_id, updated_by=system_user_id
    )

    assert version.rza_instruction_id is None
    assert version.version_number is None
    assert version.effective_date is None
    assert version.change_description is None
    assert version.change_justification is None
    assert version.created_by == system_user_id
    assert version.scan_file_id is None
    assert version.editable_file_id is None
