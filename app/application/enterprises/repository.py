from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enterprise import Enterprise


class EnterpriseRepository:
    """Работа с предприятиями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, enterprise_id: UUID) -> Enterprise | None:
        return await self.session.get(Enterprise, enterprise_id)

    async def is_ancestor_or_same(
            self,
            ancestor_id: UUID,
            enterprise_id: UUID,
    ) -> bool:
        """Проверяет, является ли предприятие предком или самим предприятием."""

        if ancestor_id == enterprise_id:
            enterprise = await self.get_by_id(enterprise_id)
            return enterprise is not None and enterprise.deleted_at is None

        enterprise_tree = (
            select(
                Enterprise.id,
                Enterprise.parent_id,
            )
            .where(
                Enterprise.id == enterprise_id,
                Enterprise.deleted_at.is_(None),
            )
            .cte(name="enterprise_tree", recursive=True)
        )

        enterprise_tree = enterprise_tree.union_all(
            select(
                Enterprise.id,
                Enterprise.parent_id,
            )
            .join(
                enterprise_tree,
                Enterprise.id == enterprise_tree.c.parent_id,
            )
            .where(Enterprise.deleted_at.is_(None))
        )

        query = select(enterprise_tree.c.id).where(
            enterprise_tree.c.id == ancestor_id
        )

        result = await self.session.scalar(query)

        return result is not None