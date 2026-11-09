from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


class EnterpriseRepository:
    """Работа с предприятиями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет сессию для запросов к организационной структуре.
            
            Args:
            session: Асинхронная SQLAlchemy-сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(self, enterprise_id: UUID) -> Enterprise | None:
        """Находит предприятие по идентификатору, включая архивные записи.
            
            Args:
            enterprise_id: Идентификатор предприятия.
            
            Returns:
            Предприятие или None, если запись отсутствует.
        """
        return await self.session.get(Enterprise, enterprise_id)

    async def get_all_active(self) -> list[Enterprise]:
        """Возвращает все неудалённые предприятия."""
        result = await self.session.scalars(
            select(Enterprise)
            .where(Enterprise.deleted_at.is_(None))
            .order_by(Enterprise.full_name)
        )

        return list(result)

    async def get_all_for_access_scope(self) -> list[Enterprise]:
        """Возвращает все предприятия, включая архивные.
            
            Метод используется для проверок областей доступа, которым требуется
            учитывать существующие записи независимо от признака архивирования.
            
            Returns:
            Список предприятий, отсортированный по полному наименованию.
        """
        result = await self.session.scalars(
            select(Enterprise).order_by(Enterprise.full_name)
        )
        return list(result)

    async def is_ancestor_or_same(
        self,
        ancestor_id: UUID,
        enterprise_id: UUID,
    ) -> bool:
        """Проверяет, входит ли предприятие в поддерево заданного предка.
            
            Проверка выполняется рекурсивным CTE по parent_id. Архивные предприятия
            исключаются из цепочки; совпадение идентификаторов также требует,
            чтобы сама запись существовала и не была архивирована.
            
            Args:
            ancestor_id: Идентификатор предполагаемого предка.
            enterprise_id: Идентификатор проверяемого предприятия.
            
            Returns:
            True, если предок совпадает с предприятием или находится выше
            него в активной иерархии, иначе False.
        """

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

    async def save(self, enterprise: Enterprise) -> Enterprise:
        """Добавляет или сохраняет предприятие и выполняет flush.
            
            Транзакция не фиксируется; commit выполняется внешним уровнем.
            
            Args:
            enterprise: Модель предприятия.
            
            Returns:
            Та же модель предприятия.
        """
        self.session.add(enterprise)
        await self.session.flush()
        return enterprise

    async def get_by_parent_and_type(
        self,
        *,
        parent_id: UUID | None,
        enterprise_type: EnterpriseType,
    ) -> list[Enterprise]:
        """Возвращает предприятия с указанным родителем и типом.
            
            Args:
            parent_id: Идентификатор родителя; None для корневых предприятий.
            enterprise_type: Тип предприятия.
            
            Returns:
            Подходящие предприятия, отсортированные по полному наименованию.
        """
        result = await self.session.scalars(
            select(Enterprise)
            .where(
                Enterprise.parent_id == parent_id
                if parent_id is not None
                else Enterprise.parent_id.is_(None),
                Enterprise.type == enterprise_type,
            )
            .order_by(Enterprise.full_name)
        )
        return list(result)