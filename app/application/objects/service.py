from uuid import UUID

from app.application.access.service import AccessService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.resolver import ObjectResolver
from app.application.objects.schemas import SelectedObject


class ObjectService:
    def __init__(
        self,
        access_service: AccessService,
        object_resolver: ObjectResolver,
    ) -> None:
        self.access_service = access_service
        self.object_resolver = object_resolver

    async def get_object(
        self,
        user_id: UUID,
        object_type: str,
        object_id: UUID,
    ) -> SelectedObject:
        if object_type == "substation":
            has_access = await self.access_service.can_access_substation(
                user_id=user_id,
                substation_id=object_id,
            )
        elif object_type == "connection":
            has_access = await self.access_service.can_access_connection(
                user_id=user_id,
                connection_id=object_id,
            )
        elif object_type == "urza":
            has_access = await self.access_service.can_access_urza(
                user_id=user_id,
                urza_id=object_id,
            )
        else:
            raise ObjectNotFoundError

        if not has_access:
            raise ObjectAccessDeniedError

        selected_object = await self.object_resolver.resolve(
            object_type=object_type,
            object_id=object_id,
        )

        if selected_object is None:
            raise ObjectNotFoundError

        return selected_object