from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


class URZAInstructionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        instruction_id: UUID,
    ) -> URZAInstruction | None:
        return await self.session.scalar(
            select(URZAInstruction).where(
                URZAInstruction.id == instruction_id,
                URZAInstruction.deleted_at.is_(None),
            )
        )

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> URZAInstruction | None:
        query = select(URZAInstruction).where(
            URZAInstruction.urza_id == urza_id,
            URZAInstruction.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> URZAInstructionVersion | None:
        query = select(URZAInstructionVersion).where(
            URZAInstructionVersion.id == version_id,
            URZAInstructionVersion.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def add_instruction(
        self,
        instruction: URZAInstruction,
    ) -> URZAInstruction:
        self.session.add(instruction)
        await self.session.flush()
        return instruction

    async def add_version(
        self,
        version: URZAInstructionVersion,
    ) -> URZAInstructionVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def save(
        self,
        version: URZAInstructionVersion,
    ) -> URZAInstructionVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_current_version(
            self,
            instruction_id: UUID,
    ) -> URZAInstructionVersion | None:
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id
                == instruction_id,
                URZAInstructionVersion.status == DocumentStatus.APPROVED,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(
                URZAInstructionVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_max_version_number(
        self,
        instruction_id: UUID,
    ) -> int | None:
        query = select(func.max(URZAInstructionVersion.version_number)).where(
            URZAInstructionVersion.urza_instruction_id == instruction_id,
        )
        return await self.session.scalar(query)

    async def get_max_published_version_number(
        self,
        instruction_id: UUID,
    ) -> int | None:
        query = select(func.max(URZAInstructionVersion.version_number)).where(
            URZAInstructionVersion.urza_instruction_id == instruction_id,
            URZAInstructionVersion.status == DocumentStatus.APPROVED,
        )
        return await self.session.scalar(query)

    async def lock_instruction_for_versioning(
        self,
        instruction_id: UUID,
    ) -> None:
        await self.session.scalar(
            select(URZAInstruction.id)
            .where(URZAInstruction.id == instruction_id)
            .with_for_update()
        )

    async def lock_and_refresh_version(
        self,
        version: URZAInstructionVersion,
    ) -> None:
        await self.lock_instruction_for_versioning(
            version.urza_instruction_id,
        )
        await self.session.refresh(version)

    async def assign_next_published_number(
        self,
        version: URZAInstructionVersion,
    ) -> int:
        instruction_id = version.urza_instruction_id
        await self.lock_instruction_for_versioning(instruction_id)
        published_max = await self.get_max_published_version_number(
            instruction_id,
        )
        next_number = (published_max or 0) + 1

        conflict = await self.session.scalar(
            select(URZAInstructionVersion).where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.version_number == next_number,
                URZAInstructionVersion.id != version.id,
            )
        )
        if conflict is not None:
            max_number = await self.get_max_version_number(instruction_id)
            conflict.version_number = (max_number or 0) + 1
            await self.session.flush()

        return next_number

    async def get_latest_working_version(
        self,
        instruction_id: UUID,
    ) -> URZAInstructionVersion | None:
        query = (
            select(URZAInstructionVersion)
            .options(selectinload(URZAInstructionVersion.creator))
            .where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(URZAInstructionVersion.version_number.desc())
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_working_versions(
        self,
        instruction_id: UUID,
    ) -> list[URZAInstructionVersion]:
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
                selectinload(URZAInstructionVersion.scan_file),
                selectinload(URZAInstructionVersion.editable_file),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id == instruction_id,
                URZAInstructionVersion.deleted_at.is_(None),
                URZAInstructionVersion.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .order_by(
                URZAInstructionVersion.created_at.desc(),
                URZAInstructionVersion.id.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_versions(
            self,
            instruction_id: UUID,
    ) -> list[URZAInstructionVersion]:
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.creator),
                selectinload(URZAInstructionVersion.scan_file),
                selectinload(URZAInstructionVersion.editable_file),
            )
            .where(
                URZAInstructionVersion.urza_instruction_id
                == instruction_id,
                URZAInstructionVersion.status == DocumentStatus.APPROVED,
                URZAInstructionVersion.deleted_at.is_(None),
            )
            .order_by(
                URZAInstructionVersion.version_number.desc(),
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def list_standalone_work_items(self) -> list[URZAInstructionVersion]:
        query = (
            select(URZAInstructionVersion)
            .options(
                selectinload(URZAInstructionVersion.urza_instruction),
                selectinload(URZAInstructionVersion.creator),
            )
            .where(
                URZAInstructionVersion.deleted_at.is_(None),
                URZAInstructionVersion.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .order_by(
                URZAInstructionVersion.created_at.desc(),
                URZAInstructionVersion.id.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())
