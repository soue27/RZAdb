from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


class RZAInstructionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        instruction_id: UUID,
    ) -> RZAInstruction | None:
        return await self.session.get(
            RZAInstruction,
            instruction_id,
        )

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> RZAInstruction | None:
        query = select(RZAInstruction).where(
            RZAInstruction.substation_id == substation_id,
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> RZAInstructionVersion | None:
        return await self.session.get(
            RZAInstructionVersion,
            version_id,
        )

    async def add_instruction(
        self,
        instruction: RZAInstruction,
    ) -> RZAInstruction:
        self.session.add(instruction)
        await self.session.flush()
        return instruction

    async def add_version(
        self,
        version: RZAInstructionVersion,
    ) -> RZAInstructionVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_current_version(
        self,
        instruction_id: UUID,
    ) -> RZAInstructionVersion | None:
        query = (
            select(RZAInstructionVersion)
            .where(
                RZAInstructionVersion.rza_instruction_id
                == instruction_id,
            )
            .order_by(
                RZAInstructionVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)
