from uuid import UUID

from app.application.connections.repository import ConnectionRepository
from app.application.connections.schemas import (
    ConnectionDetails,
    ConnectionListItem,
)


class ConnectionService:
    """Бизнес-логика работы с присоединениями."""

    def __init__(self, repository: ConnectionRepository) -> None:
        self.repository = repository

    async def get_by_id(
        self,
        connection_id: UUID,
    ) -> ConnectionDetails | None:
        connection = await self.repository.get_by_id(connection_id)

        if connection is None:
            return None

        return ConnectionDetails(
            id=connection.id,
            dispatch_name=connection.dispatch_name,
            sap_code=connection.sap_code,
            asureo_code=connection.asureo_code,
            rdu_subordination=connection.rdu_subordination,
            operational_current_type=connection.operational_current_type,
        )

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[ConnectionListItem]:
        connections = await self.repository.get_by_substation_ids(
            {substation_id},
        )

        return [
            ConnectionListItem(
                id=connection.id,
                dispatch_name=connection.dispatch_name,
                sap_code=connection.sap_code,
                asureo_code=connection.asureo_code,
                rdu_subordination=connection.rdu_subordination,
                operational_current_type=connection.operational_current_type,
            )
            for connection in connections
        ]