from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.file import File


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        file_id: UUID,
    ) -> File | None:
        return await self.session.get(
            File,
            file_id,
        )

    async def get_by_s3_key(
        self,
        s3_key: str,
    ) -> File | None:
        query = select(File).where(
            File.s3_key == s3_key,
        )

        return await self.session.scalar(query)

    async def add(
        self,
        file: File,
    ) -> File:
        self.session.add(file)
        await self.session.flush()

        return file

    async def save(
            self,
            file: File,
    ) -> File:
        await self.session.flush()
        return file