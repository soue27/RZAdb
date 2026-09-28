from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class FileOwnerType(StrEnum):
    SETTINGS_RECORD = "settings_record"
    SCHEMA_RECORD = "schema_record"
    TO_RECORD = "to_record"
    PROGRAM = "program"
    URZA_INSTRUCTION_VERSION = "urza_instruction_version"
    RZA_INSTRUCTION_VERSION = "rza_instruction_version"
    SELECTIVITY_SCHEME_VERSION = "selectivity_scheme_version"
    INSPECTION = "inspection"


class FileAccessTargetType(StrEnum):
    URZA = "urza"
    SUBSTATION = "substation"


@dataclass(frozen=True)
class FileOwner:
    owner_type: FileOwnerType
    owner_id: UUID
    access_target_type: FileAccessTargetType
    access_target_id: UUID
