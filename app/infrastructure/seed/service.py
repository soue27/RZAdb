from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


class RZACSVSeedService:
    """Импортирует тестовые данные РЗА из подготовленных CSV-строк."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_holding(
        self,
        row: dict[str, str],
    ) -> Enterprise:
        """Находит существующий Holding или создаёт новый."""

        full_name = row["holding_full_name"].strip()

        result = await self.session.execute(
            select(Enterprise).where(
                Enterprise.type == EnterpriseType.HOLDING,
                Enterprise.full_name == full_name,
                Enterprise.deleted_at.is_(None),
            )
        )

        holding = result.scalar_one_or_none()

        if holding is not None:
            return holding

        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name=full_name,
            short_name=row["holding_short_name"].strip(),
            sap_code=self._optional_string(row.get("holding_sap_code")),
        )

        self.session.add(holding)

        await self.session.flush()

        return holding

    @staticmethod
    def _optional_string(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None