import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_user_email_must_be_unique() -> None:
    async with async_session_factory() as session:
        first_user = User(
            full_name="Первый Пользователь",
            role=UserRole.ENGINEER,
            email="same@test.local",
            password_hash="hash-1",
            access_category=AccessCategory.III,
            active=True,
        )

        second_user = User(
            full_name="Второй Пользователь",
            role=UserRole.MANAGER,
            email="same@test.local",
            password_hash="hash-2",
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add(first_user)
        await session.flush()

        session.add(second_user)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()