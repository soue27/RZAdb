from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User
from app.domain.enums import UserRole

class UserRepository:
    """Работа с пользователями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        # Используем PK-запрос SQLAlchemy — для проверки прав этого достаточно.
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        return await self.session.scalar(query)

    async def get_active_engineers_by_enterprise(
            self,
            enterprise_id: UUID,
    ) -> list[User]:
        query = (
            select(User)
            .where(
                User.enterprise_id == enterprise_id,
                User.role == UserRole.ENGINEER,
                User.active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name)
        )

        result = await self.session.scalars(query)

        return list(result.all())