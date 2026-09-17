from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        return await self.session.get(
            URZAInstruction,
            instruction_id,
        )

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> URZAInstruction | None:
        query = select(URZAInstruction).where(
            URZAInstruction.urza_id == urza_id,
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> URZAInstructionVersion | None:
        return await self.session.get(
            URZAInstructionVersion,
            version_id,
        )

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

    async def get_current_version(
        self,
        instruction_id: UUID,
    ) -> URZAInstructionVersion | None:
        query = (
            select(URZAInstructionVersion)
            .where(
                URZAInstructionVersion.urza_instruction_id
                == instruction_id,
            )
            .order_by(
                URZAInstructionVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)