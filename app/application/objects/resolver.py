from uuid import UUID

from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.objects.schemas import SelectedObject
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository


class ObjectResolver:
    def __init__(
        self,
        substation_repository: SubstationRepository,
        connection_repository: ConnectionRepository,
        urza_repository: URZARepository,
        enterprise_repository: EnterpriseRepository,
    ) -> None:
        self.substation_repository = substation_repository
        self.connection_repository = connection_repository
        self.urza_repository = urza_repository
        self.enterprise_repository = enterprise_repository

    async def resolve(
        self,
        object_type: str,
        object_id: UUID,
        *,
        include_archived: bool = False,
    ) -> SelectedObject | None:
        if object_type == "department":
            enterprise = await self.enterprise_repository.get_by_id(object_id)

            if (
                enterprise is None
                or enterprise.deleted_at is not None
                or enterprise.type.value != "department"
            ):
                return None

            return SelectedObject(
                object_type="department",
                id=enterprise.id,
                name=enterprise.full_name,
            )

        if object_type == "substation":
            substation = await self.substation_repository.get_by_id(object_id)

            if substation is not None and substation.deleted_at is not None and not include_archived:
                return None

            if substation is None:
                return None

            return SelectedObject(
                object_type="substation",
                id=substation.id,
                name=substation.dispatch_name,
                is_archived=substation.deleted_at is not None,
            )

        if object_type == "connection":
            connection = await self.connection_repository.get_by_id(object_id)

            if connection is not None and connection.deleted_at is not None and not include_archived:
                return None

            if connection is None:
                return None

            return SelectedObject(
                object_type="connection",
                id=connection.id,
                name=connection.dispatch_name,
                is_archived=connection.deleted_at is not None,
            )

        if object_type == "urza":
            urza = (
                await self.urza_repository.get_by_id_including_deleted(object_id)
                if include_archived
                else await self.urza_repository.get_by_id(object_id)
            )

            if urza is None:
                return None

            return SelectedObject(
                object_type="urza",
                id=urza.id,
                name=urza.dispatch_name,
                is_archived=urza.deleted_at is not None,
            )

        return None
