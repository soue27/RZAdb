from uuid import UUID

from app.application.access.service import AccessService
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.owners import FileAccessTargetType
from app.application.files.repository import FileRepository
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.file import File


class FileAccessService:
    def __init__(
        self,
        *,
        file_repository: FileRepository,
        owner_resolver: FileOwnerResolver,
        access_service: AccessService,
    ) -> None:
        self.file_repository = file_repository
        self.owner_resolver = owner_resolver
        self.access_service = access_service

    async def get_accessible_file(
        self,
        user_id: UUID,
        file_id: UUID,
    ) -> File:
        file = await self.file_repository.get_by_id(file_id)
        if file is None:
            raise ObjectNotFoundError

        if file.deleted_at is not None:
            raise ObjectAccessDeniedError

        owner = await self.owner_resolver.resolve(file_id)
        if owner is None:
            raise ObjectNotFoundError

        if owner.access_target_type is FileAccessTargetType.URZA:
            has_access = await self.access_service.can_access_urza(
                user_id=user_id,
                urza_id=owner.access_target_id,
            )
        elif owner.access_target_type is FileAccessTargetType.SUBSTATION:
            has_access = await self.access_service.can_access_substation(
                user_id=user_id,
                substation_id=owner.access_target_id,
            )
        else:
            raise ValueError(
                f"Unsupported file access target: {owner.access_target_type}"
            )

        if not has_access:
            raise ObjectAccessDeniedError

        return file
