from datetime import UTC, date, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from uuid6 import uuid7

from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.owner_repository import FileOwnerRepository
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.owners import FileAccessTargetType, FileOwnerType
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    MaintenanceType,
    OperationalCurrentType,
    ProgramType,
    RoomCategory,
    TaskStatus,
    URZACategory,
    URZAStatus,
)
from app.domain.file import File
from app.domain.inspection import Inspection
from app.domain.inspection_task import InspectionTask
from app.domain.maintenance import TORecord
from app.domain.program import Program
from app.domain.rza_instruction import RZAInstruction, RZAInstructionVersion
from app.domain.rza_settings import SettingsForm
from app.domain.schema import SchemaForm, SchemaRecord
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)
from app.domain.settings_record import SettingsRecord
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)
from app.infrastructure.database.engine import async_session_factory


def _new_file(system_user_id: UUID, *, deleted: bool = False) -> File:
    file = File(
        id=uuid7(),
        s3_key=f"files/resolver/{uuid7()}.pdf",
        original_name="record.pdf",
        display_name="Record",
        extension=".pdf",
        size=1,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    if deleted:
        file.deleted_at = datetime.now(UTC)
    return file


@pytest_asyncio.fixture
async def owner_data(system_user_id):
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Resolver Department",
            short_name="RESOLVER",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            operational_current_type=OperationalCurrentType.PERMANENT,
            dispatch_name="Resolver PS",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        connection = Connection(
            substation=substation,
            dispatch_name="Resolver connection",
            rdu_subordination=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        urza = URZA(
            connection=connection,
            dispatch_name="Resolver URZA",
            rdu_subordination=False,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        urza.deleted_at = datetime.now(UTC)
        substation.deleted_at = datetime.now(UTC)

        files = {
            role: _new_file(system_user_id, deleted=role == "program_scan")
            for role in (
                "settings",
                "schema_scan",
                "schema_editable",
                "schema_signed",
                "to_scan",
                "to_editable",
                "to_signed",
                "program_scan",
                "program_editable",
                "urza_instruction_scan",
                "urza_instruction_editable",
                "rza_instruction_scan",
                "rza_instruction_editable",
                "selectivity_scan",
                "selectivity_editable",
                "inspection_scan",
                "inspection_editable",
                "orphan",
                "archived_file",
            )
        }

        settings_form = SettingsForm(
            urza=urza,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        settings = SettingsRecord(
            settings_form=settings_form,
            change_date=date(2026, 1, 1),
            parameter_name="P",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file=files["settings"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        schema_form = SchemaForm(
            urza=urza,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        schema = SchemaRecord(
            schema_form=schema_form,
            schema_number="S-1",
            schema_name="Schema",
            change_description="Change",
            change_justification="Reason",
            upload_date=date(2026, 1, 1),
            scan_file=files["schema_scan"],
            editable_file=files["schema_editable"],
            signed_form_file=files["schema_signed"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        to_record = TORecord(
            urza=urza,
            maintenance_date=date(2026, 1, 1),
            maintenance_type=MaintenanceType.K,
            scan_protocol=files["to_scan"],
            editable_protocol=files["to_editable"],
            signed_form_file=files["to_signed"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        program = Program(
            urza=urza,
            program_type=ProgramType.WORK,
            program_number="P-1",
            scan_file=files["program_scan"],
            editable_file=files["program_editable"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        urza_instruction = URZAInstruction(
            urza=urza,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        urza_instruction_version = URZAInstructionVersion(
            urza_instruction=urza_instruction,
            version_number=1,
            effective_date=date(2026, 1, 1),
            scan_file=files["urza_instruction_scan"],
            editable_file=files["urza_instruction_editable"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        rza_instruction = RZAInstruction(
            substation=substation,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        rza_instruction_version = RZAInstructionVersion(
            rza_instruction=rza_instruction,
            version_number=1,
            effective_date=date(2026, 1, 1),
            scan_file=files["rza_instruction_scan"],
            editable_file=files["rza_instruction_editable"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        selectivity_scheme = SelectivityScheme(
            substation=substation,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        selectivity_version = SelectivitySchemeVersion(
            selectivity_scheme=selectivity_scheme,
            version_number=1,
            number="SS-1",
            name="Scheme",
            effective_date=date(2026, 1, 1),
            scan_file=files["selectivity_scan"],
            editable_file=files["selectivity_editable"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        inspection_task = InspectionTask(
            substation=substation,
            status=TaskStatus.COMPLETED,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        inspection = Inspection(
            substation=substation,
            inspection_task=inspection_task,
            inspection_date=date(2026, 1, 1),
            remarks="No remarks",
            scan_file=files["inspection_scan"],
            editable_file=files["inspection_editable"],
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        session.add_all(
            [
                department,
                *files.values(),
                settings,
                schema,
                to_record,
                program,
                urza_instruction_version,
                rza_instruction_version,
                selectivity_version,
                inspection,
            ]
        )
        await session.flush()

        yield session, files, {
            "settings": (FileOwnerType.SETTINGS_RECORD, settings.id, urza.id),
            "schema_scan": (FileOwnerType.SCHEMA_RECORD, schema.id, urza.id),
            "schema_editable": (FileOwnerType.SCHEMA_RECORD, schema.id, urza.id),
            "schema_signed": (FileOwnerType.SCHEMA_RECORD, schema.id, urza.id),
            "to_scan": (FileOwnerType.TO_RECORD, to_record.id, urza.id),
            "to_editable": (FileOwnerType.TO_RECORD, to_record.id, urza.id),
            "to_signed": (FileOwnerType.TO_RECORD, to_record.id, urza.id),
            "program_scan": (FileOwnerType.PROGRAM, program.id, urza.id),
            "program_editable": (FileOwnerType.PROGRAM, program.id, urza.id),
            "urza_instruction_scan": (
                FileOwnerType.URZA_INSTRUCTION_VERSION,
                urza_instruction_version.id,
                urza.id,
            ),
            "urza_instruction_editable": (
                FileOwnerType.URZA_INSTRUCTION_VERSION,
                urza_instruction_version.id,
                urza.id,
            ),
            "rza_instruction_scan": (
                FileOwnerType.RZA_INSTRUCTION_VERSION,
                rza_instruction_version.id,
                substation.id,
            ),
            "rza_instruction_editable": (
                FileOwnerType.RZA_INSTRUCTION_VERSION,
                rza_instruction_version.id,
                substation.id,
            ),
            "selectivity_scan": (
                FileOwnerType.SELECTIVITY_SCHEME_VERSION,
                selectivity_version.id,
                substation.id,
            ),
            "selectivity_editable": (
                FileOwnerType.SELECTIVITY_SCHEME_VERSION,
                selectivity_version.id,
                substation.id,
            ),
            "inspection_scan": (
                FileOwnerType.INSPECTION,
                inspection.id,
                substation.id,
            ),
            "inspection_editable": (
                FileOwnerType.INSPECTION,
                inspection.id,
                substation.id,
            ),
        }
        await session.rollback()


@pytest.mark.asyncio
async def test_resolves_all_explicit_file_foreign_keys(owner_data) -> None:
    session, files, expected = owner_data
    resolver = FileOwnerResolver(FileOwnerRepository(session))

    for role, file in files.items():
        if role in {"orphan", "archived_file"}:
            continue

        resolved = await resolver.resolve(file.id)

        assert resolved is not None
        expected_type, expected_owner_id, expected_target_id = expected[role]
        assert resolved.owner_type is expected_type
        assert resolved.owner_id == expected_owner_id
        assert resolved.access_target_id == expected_target_id
        expected_target_type = (
            FileAccessTargetType.URZA
            if expected_type in {
                FileOwnerType.SETTINGS_RECORD,
                FileOwnerType.SCHEMA_RECORD,
                FileOwnerType.TO_RECORD,
                FileOwnerType.PROGRAM,
                FileOwnerType.URZA_INSTRUCTION_VERSION,
            }
            else FileAccessTargetType.SUBSTATION
        )
        assert resolved.access_target_type is expected_target_type


@pytest.mark.asyncio
async def test_resolves_orphan_as_no_owner(owner_data) -> None:
    session, files, _ = owner_data
    resolver = FileOwnerResolver(FileOwnerRepository(session))

    assert await resolver.resolve(files["orphan"].id) is None


@pytest.mark.asyncio
async def test_resolves_archived_file_and_archived_domain_owners(owner_data) -> None:
    session, files, _ = owner_data
    resolver = FileOwnerResolver(FileOwnerRepository(session))

    owner = await resolver.resolve(files["program_scan"].id)
    assert owner is not None
    assert files["program_scan"].deleted_at is not None
    assert owner.access_target_type is FileAccessTargetType.URZA

    owner = await resolver.resolve(files["rza_instruction_scan"].id)
    assert owner is not None
    assert owner.access_target_type is FileAccessTargetType.SUBSTATION


@pytest.mark.asyncio
async def test_same_owner_can_reference_file_in_multiple_roles(
    owner_data,
    system_user_id,
) -> None:
    session, _, expected = owner_data
    shared_file = _new_file(system_user_id)
    program = Program(
        urza_id=expected["program_scan"][2],
        program_type=ProgramType.WORK,
        program_number="P-duplicate-role",
        scan_file=shared_file,
        editable_file=shared_file,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    session.add_all([shared_file, program])
    await session.flush()

    owner = await FileOwnerResolver(FileOwnerRepository(session)).resolve(
        shared_file.id,
    )

    assert owner is not None
    assert owner.owner_type is FileOwnerType.PROGRAM
    assert owner.owner_id == program.id


@pytest.mark.asyncio
async def test_different_owner_objects_are_ambiguous(
    owner_data,
    system_user_id,
) -> None:
    session, files, _ = owner_data
    shared_file = _new_file(system_user_id)
    original_program_owner = await FileOwnerRepository(
        session,
    ).get_owners_by_file_id(files["program_scan"].id)
    second_program = Program(
        urza_id=original_program_owner[0].access_target_id,
        program_type=ProgramType.WORK,
        program_number="P-second-owner",
        scan_file=shared_file,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    first_program = await session.get(Program, original_program_owner[0].owner_id)
    first_program.editable_file = shared_file
    session.add_all([shared_file, second_program])
    await session.flush()

    with pytest.raises(AmbiguousFileOwnershipError):
        await FileOwnerResolver(FileOwnerRepository(session)).resolve(
            shared_file.id,
        )


@pytest.mark.asyncio
async def test_different_owner_types_are_ambiguous(
    owner_data,
    system_user_id,
) -> None:
    session, files, expected = owner_data
    shared_file = _new_file(system_user_id)
    program = Program(
        urza_id=expected["program_scan"][2],
        program_type=ProgramType.WORK,
        program_number="P-cross-type",
        scan_file=shared_file,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    to_record = TORecord(
        urza_id=expected["program_scan"][2],
        maintenance_date=date(2026, 1, 2),
        maintenance_type=MaintenanceType.K,
        signed_form_file=shared_file,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    session.add_all([shared_file, program, to_record])
    await session.flush()

    with pytest.raises(AmbiguousFileOwnershipError):
        await FileOwnerResolver(FileOwnerRepository(session)).resolve(
            shared_file.id,
        )
