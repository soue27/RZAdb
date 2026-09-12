from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.domain.file import File
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_file_can_be_persisted() -> None:
    uploaded_at = datetime.now(timezone.utc)
    s3_key = f"files/test/{uuid4()}.pdf"

    async with async_session_factory() as session:
        file = File(
            s3_key=s3_key,
            original_name="scan_001.pdf",
            display_name="ПС Тестовая_Ввод 110 кВ_ТО_2026-09-12.pdf",
            extension=".pdf",
            size=1024,
            mime_type="application/pdf",
            uploaded_at=uploaded_at,
        )

        session.add(file)
        await session.commit()

        file_id = file.id

        result = await session.execute(
            select(File).where(File.id == file_id)
        )
        saved_file = result.scalar_one()

        assert saved_file.s3_key == s3_key
        assert saved_file.original_name == "scan_001.pdf"
        assert (
            saved_file.display_name
            == "ПС Тестовая_Ввод 110 кВ_ТО_2026-09-12.pdf"
        )
        assert saved_file.extension == ".pdf"
        assert saved_file.size == 1024
        assert saved_file.mime_type == "application/pdf"
        assert saved_file.uploaded_at == uploaded_at