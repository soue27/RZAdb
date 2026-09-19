from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.program import Program


class ProgramRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        program_id: UUID,
    ) -> Program | None:
        return await self.session.get(
            Program,
            program_id,
        )

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> list[Program]:
        query = (
            select(Program)
            .where(
                Program.urza_id == urza_id,
            )
            .order_by(
                Program.program_number,
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def get_by_task_id(
        self,
        task_id: UUID,
    ) -> Program | None:
        query = select(Program).where(
            Program.task_id == task_id,
        )

        return await self.session.scalar(query)

    async def add(
        self,
        program: Program,
    ) -> Program:
        self.session.add(program)
        await self.session.flush()

        return program