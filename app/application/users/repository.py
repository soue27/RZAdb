from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserRole
from app.domain.user import User


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

    async def get_active_inspection_assignees_by_enterprise(
        self, enterprise_id: UUID
    ) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .where(
                User.enterprise_id == enterprise_id,
                User.role.in_([UserRole.ENGINEER, UserRole.MANAGER]),
                User.active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name)
        )
        return list(result.all())

    async def get_all(self) -> list[User]:
        """Возвращает всех пользователей с данными их предприятий."""
        query = (
            select(User)
            .options(selectinload(User.enterprise))
            .order_by(User.full_name, User.email)
        )
        result = await self.session.scalars(query)
        return list(result.all())

