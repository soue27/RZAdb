from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    EnterpriseType,
)
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.seed.parser import CSVRowParser


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

    async def get_or_create_branch(
        self,
        row: dict[str, str],
        holding_id: UUID,
    ) -> Enterprise:
        """Находит существующий филиал или создаёт новый."""

        full_name = row["branch_full_name"].strip()

        result = await self.session.execute(
            select(Enterprise).where(
                Enterprise.type == EnterpriseType.BRANCH,
                Enterprise.parent_id == holding_id,
                Enterprise.full_name == full_name,
                Enterprise.deleted_at.is_(None),
            )
        )

        branch = result.scalar_one_or_none()

        if branch is not None:
            return branch

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            parent_id=holding_id,
            full_name=full_name,
            short_name=row["branch_short_name"].strip(),
            sap_code=self._optional_string(row.get("branch_sap_code")),
        )

        self.session.add(branch)

        await self.session.flush()

        return branch

    async def get_or_create_department(
        self,
        row: dict[str, str],
        branch_id: UUID,
    ) -> Enterprise:
        """Находит существующее производственное отделение или создаёт новое."""

        full_name = row["department_full_name"].strip()

        result = await self.session.execute(
            select(Enterprise).where(
                Enterprise.type == EnterpriseType.DEPARTMENT,
                Enterprise.parent_id == branch_id,
                Enterprise.full_name == full_name,
                Enterprise.deleted_at.is_(None),
            )
        )

        department = result.scalar_one_or_none()

        if department is not None:
            return department

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            parent_id=branch_id,
            full_name=full_name,
            short_name=row["department_short_name"].strip(),
            sap_code=self._optional_string(
                row.get("department_sap_code")
            ),
        )

        self.session.add(department)

        await self.session.flush()

        return department

    async def get_or_create_substation(
        self,
        row: dict[str, str],
        department_id: UUID,
    ) -> Substation:
        """Находит существующую подстанцию или создаёт новую."""

        dispatch_name = row["substation_dispatch_name"].strip()

        result = await self.session.execute(
            select(Substation).where(
                Substation.enterprise_id == department_id,
                Substation.dispatch_name == dispatch_name,
                Substation.deleted_at.is_(None),
            )
        )

        substation = result.scalar_one_or_none()

        if substation is not None:
            return substation

        substation = Substation(
            enterprise_id=department_id,
            highest_voltage=CSVRowParser.highest_voltage(
                row["substation_highest_voltage"]
            ),
            dispatch_name=dispatch_name,
            sap_code=CSVRowParser.optional_string(
                row.get("substation_sap_code", "")
            ),
            asureo_code=CSVRowParser.optional_string(
                row.get("substation_asureo_code", "")
            ),
            latitude=CSVRowParser.decimal(
                row.get("substation_latitude", "")
            ),
            longitude=CSVRowParser.decimal(
                row.get("substation_longitude", "")
            ),
            address=CSVRowParser.optional_string(
                row.get("substation_address", "")
            ),
        )

        self.session.add(substation)

        await self.session.flush()

        return substation

    async def get_or_create_connection(
            self,
            row: dict[str, str],
            substation_id: UUID,
    ) -> Connection:
        """Находит существующее присоединение или создаёт новое."""

        dispatch_name = row["connection_dispatch_name"].strip()

        result = await self.session.execute(
            select(Connection).where(
                Connection.substation_id == substation_id,
                Connection.dispatch_name == dispatch_name,
                Connection.deleted_at.is_(None),
            )
        )

        connection = result.scalar_one_or_none()

        if connection is not None:
            return connection

        connection = Connection(
            substation_id=substation_id,
            dispatch_name=dispatch_name,
            sap_code=CSVRowParser.optional_string(
                row.get("connection_sap_code", "")
            ),
            asureo_code=CSVRowParser.optional_string(
                row.get("connection_asureo_code", "")
            ),
            rdu_subordination=CSVRowParser.boolean(
                row["connection_rdu_subordination"]
            ),
            operational_current_type=CSVRowParser.operational_current_type(
                row["operational_current_type"]
            ),
        )

        self.session.add(connection)

        await self.session.flush()

        return connection

    async def get_or_create_urza(
            self,
            row: dict[str, str],
            connection_id: UUID,
    ) -> URZA:
        """Находит существующую УРЗА или создаёт новую."""

        dispatch_name = row["urza_dispatch_name"].strip()

        result = await self.session.execute(
            select(URZA).where(
                URZA.connection_id == connection_id,
                URZA.dispatch_name == dispatch_name,
                URZA.deleted_at.is_(None),
            )
        )

        urza = result.scalar_one_or_none()

        if urza is not None:
            return urza

        urza = URZA(
            connection_id=connection_id,
            dispatch_name=dispatch_name,
            rdu_subordination=CSVRowParser.boolean(
                row["urza_rdu_subordination"]
            ),
            inventory_number=CSVRowParser.optional_string(
                row.get("urza_inventory_number", "")
            ),
            commissioning_date=CSVRowParser.date(
                row["urza_commissioning_date"]
            ),
            status=CSVRowParser.urza_status(row["urza_status"]),
            element_base=CSVRowParser.element_base(row["urza_element_base"]),
            category=CSVRowParser.urza_category(row["urza_category"]),
            room_category=CSVRowParser.room_category(
                row["urza_room_category"]
            ),
            complexity=CSVRowParser.boolean(row["urza_complexity"]),
        )

        self.session.add(urza)

        await self.session.flush()

        return urza

    async def import_row(
        self,
        row: dict[str, str],
    ) -> URZA:
        """Импортирует одну строку CSV по всей иерархии РЗА."""

        holding = await self.get_or_create_holding(row)

        branch = await self.get_or_create_branch(
            row,
            holding_id=holding.id,
        )

        department = await self.get_or_create_department(
            row,
            branch_id=branch.id,
        )

        substation = await self.get_or_create_substation(
            row,
            department_id=department.id,
        )

        connection = await self.get_or_create_connection(
            row,
            substation_id=substation.id,
        )

        return await self.get_or_create_urza(
            row,
            connection_id=connection.id,
        )

    @staticmethod
    def _optional_string(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None