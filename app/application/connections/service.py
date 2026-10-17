from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.connections.repository import ConnectionRepository
from app.application.connections.schemas import (
    ConnectionCreate,
    ConnectionDetails,
    ConnectionListItem,
    ConnectionUpdate,
)
from app.application.objects.exceptions import ObjectNotFoundError
from app.domain.connection import Connection

_NAME_INDEX = "uq_connections_substation_dispatch_name"


class ConnectionNameConflictError(ValueError):
    """Raised when the dispatch name is already reserved in a substation."""


class ConnectionService:
    """Бизнес-логика работы с присоединениями."""

    def __init__(self, repository: ConnectionRepository) -> None:
        self.repository = repository

    async def create(
        self,
        *,
        substation_id: UUID,
        actor_id: UUID,
        data: ConnectionCreate,
    ) -> ConnectionDetails:
        if await self.repository.exists_by_name(
            substation_id,
            data.dispatch_name,
        ):
            raise ConnectionNameConflictError(
                "Присоединение с таким диспетчерским наименованием уже существует."
            )

        connection = Connection(
            substation_id=substation_id,
            dispatch_name=data.dispatch_name,
            rdu_subordination=data.rdu_subordination,
            sap_code=data.sap_code,
            asureo_code=data.asureo_code,
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            await self.repository.add(connection)
        except IntegrityError as exc:
            original = exc.orig
            constraint_name = getattr(original, "constraint_name", None)
            if constraint_name == _NAME_INDEX or _NAME_INDEX in str(original):
                raise ConnectionNameConflictError(
                    "Присоединение с таким диспетчерским наименованием уже существует."
                ) from exc
            raise

        return ConnectionDetails(
            id=connection.id,
            dispatch_name=connection.dispatch_name,
            sap_code=connection.sap_code,
            asureo_code=connection.asureo_code,
            rdu_subordination=connection.rdu_subordination,
            substation_id=connection.substation_id,
        )

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
            substation_id=connection.substation_id,
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
            )
            for connection in connections
        ]

    async def update(
            self,
            *,
            connection_id: UUID,
            actor_id: UUID,
            data: ConnectionUpdate,
    ) -> ConnectionDetails:
        connection = await self.repository.get_by_id(connection_id)

        if connection is None:
            raise ObjectNotFoundError

        if await self.repository.exists_by_name(
                connection.substation_id,
                data.dispatch_name,
                exclude_connection_id=connection_id,
        ):
            raise ConnectionNameConflictError(
                "Присоединение с таким диспетчерским наименованием уже существует."
            )

        connection.dispatch_name = data.dispatch_name
        connection.rdu_subordination = data.rdu_subordination
        connection.sap_code = data.sap_code
        connection.asureo_code = data.asureo_code
        connection.updated_by = actor_id

        try:
            await self.repository.update(connection)
        except IntegrityError as exc:
            original = exc.orig
            constraint_name = getattr(original, "constraint_name", None)
            if constraint_name == _NAME_INDEX or _NAME_INDEX in str(original):
                raise ConnectionNameConflictError(
                    "Присоединение с таким диспетчерским наименованием уже существует."
                ) from exc
            raise

        return ConnectionDetails(
            id=connection.id,
            dispatch_name=connection.dispatch_name,
            sap_code=connection.sap_code,
            asureo_code=connection.asureo_code,
            rdu_subordination=connection.rdu_subordination,
            substation_id=connection.substation_id,
        )
