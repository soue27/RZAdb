from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.files.owners import (
    FileAccessTargetType,
    FileOwner,
    FileOwnerType,
)
from app.domain.inspection import Inspection
from app.domain.maintenance import TORecord
from app.domain.program import Program
from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)
from app.domain.schema import SchemaForm, SchemaRecord
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)
from app.domain.settings_record import SettingsRecord
from app.domain.rza_settings import SettingsForm
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


class FileOwnerRepository:
    """Finds domain records that reference a file through explicit FKs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_owners_by_file_id(self, file_id: UUID) -> list[FileOwner]:
        owners: list[FileOwner] = []

        queries = (
            (
                select(SettingsRecord.id, SettingsForm.urza_id)
                .join(SettingsForm, SettingsRecord.settings_form_id == SettingsForm.id)
                .where(SettingsRecord.signed_form_file_id == file_id),
                FileOwnerType.SETTINGS_RECORD,
                FileAccessTargetType.URZA,
            ),
            (
                select(SchemaRecord.id, SchemaForm.urza_id)
                .join(SchemaForm, SchemaRecord.schema_form_id == SchemaForm.id)
                .where(
                    or_(
                        SchemaRecord.scan_file_id == file_id,
                        SchemaRecord.editable_file_id == file_id,
                        SchemaRecord.signed_form_file_id == file_id,
                    ),
                ),
                FileOwnerType.SCHEMA_RECORD,
                FileAccessTargetType.URZA,
            ),
            (
                select(TORecord.id, TORecord.urza_id).where(
                    or_(
                        TORecord.scan_protocol_id == file_id,
                        TORecord.editable_protocol_id == file_id,
                        TORecord.signed_form_file_id == file_id,
                    ),
                ),
                FileOwnerType.TO_RECORD,
                FileAccessTargetType.URZA,
            ),
            (
                select(Program.id, Program.urza_id).where(
                    or_(
                        Program.scan_file_id == file_id,
                        Program.editable_file_id == file_id,
                    ),
                ),
                FileOwnerType.PROGRAM,
                FileAccessTargetType.URZA,
            ),
            (
                select(URZAInstructionVersion.id, URZAInstruction.urza_id)
                .join(
                    URZAInstruction,
                    URZAInstructionVersion.urza_instruction_id
                    == URZAInstruction.id,
                )
                .where(
                    or_(
                        URZAInstructionVersion.scan_file_id == file_id,
                        URZAInstructionVersion.editable_file_id == file_id,
                    ),
                ),
                FileOwnerType.URZA_INSTRUCTION_VERSION,
                FileAccessTargetType.URZA,
            ),
            (
                select(
                    RZAInstructionVersion.id,
                    RZAInstruction.substation_id,
                )
                .join(
                    RZAInstruction,
                    RZAInstructionVersion.rza_instruction_id
                    == RZAInstruction.id,
                )
                .where(
                    or_(
                        RZAInstructionVersion.scan_file_id == file_id,
                        RZAInstructionVersion.editable_file_id == file_id,
                    ),
                ),
                FileOwnerType.RZA_INSTRUCTION_VERSION,
                FileAccessTargetType.SUBSTATION,
            ),
            (
                select(
                    SelectivitySchemeVersion.id,
                    SelectivityScheme.substation_id,
                )
                .join(
                    SelectivityScheme,
                    SelectivitySchemeVersion.selectivity_scheme_id
                    == SelectivityScheme.id,
                )
                .where(
                    or_(
                        SelectivitySchemeVersion.scan_file_id == file_id,
                        SelectivitySchemeVersion.editable_file_id == file_id,
                    ),
                ),
                FileOwnerType.SELECTIVITY_SCHEME_VERSION,
                FileAccessTargetType.SUBSTATION,
            ),
            (
                select(Inspection.id, Inspection.substation_id).where(
                    or_(
                        Inspection.scan_file_id == file_id,
                        Inspection.editable_file_id == file_id,
                    ),
                ),
                FileOwnerType.INSPECTION,
                FileAccessTargetType.SUBSTATION,
            ),
        )

        for query, owner_type, target_type in queries:
            result = await self.session.execute(query)
            owners.extend(
                FileOwner(
                    owner_type=owner_type,
                    owner_id=owner_id,
                    access_target_type=target_type,
                    access_target_id=target_id,
                )
                for owner_id, target_id in result.all()
            )

        return owners
