from uuid import UUID

from app.application.connections.repository import ConnectionRepository
from app.application.objects.schemas import SelectedObject
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository


class ObjectResolver:
    def __init__(
        self,
        substation_repository: SubstationRepository,
        connection_repository: ConnectionRepository,
        urza_repository: URZARepository,
    ) -> None:
        self.substation_repository = substation_repository
        self.connection_repository = connection_repository
        self.urza_repository = urza_repository

    async def resolve(
        self,
        object_type: str,
        object_id: UUID,
    ) -> SelectedObject | None:
        if object_type == "substation":
            substation = await self.substation_repository.get_by_id(object_id)

            if substation is None:
                return None

            return SelectedObject(
                object_type="substation",
                id=substation.id,
                name=substation.dispatch_name,
            )

        if object_type == "connection":
            connection = await self.connection_repository.get_by_id(object_id)

            if connection is None:
                return None

            return SelectedObject(
                object_type="connection",
                id=connection.id,
                name=connection.dispatch_name,
            )

        if object_type == "urza":
            urza = await self.urza_repository.get_by_id(object_id)

            if urza is None:
                return None

            return SelectedObject(
                object_type="urza",
                id=urza.id,
                name=urza.dispatch_name,
            )

        return None