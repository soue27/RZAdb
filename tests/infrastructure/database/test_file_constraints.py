from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.file import File
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_s3_key_must_be_unique() -> None:
    s3_key = f"files/test/{uuid4()}.pdf"

    async with async_session_factory() as session:
        first_file = File(
            s3_key=s3_key,
            original_name="first.pdf",
            display_name="Первый файл.pdf",
            extension=".pdf",
            size=1024,
            mime_type="application/pdf",
            uploaded_at=datetime.now(UTC),
        )

        second_file = File(
            s3_key=s3_key,
            original_name="second.pdf",
            display_name="Второй файл.pdf",
            extension=".pdf",
            size=2048,
            mime_type="application/pdf",
            uploaded_at=datetime.now(UTC),
        )

        session.add(first_file)
        await session.flush()

        session.add(second_file)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()