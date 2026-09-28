from uuid import UUID

from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.owner_repository import FileOwnerRepository
from app.application.files.owners import FileOwner


class FileOwnerResolver:
    def __init__(self, repository: FileOwnerRepository) -> None:
        self.repository = repository

    async def resolve(self, file_id: UUID) -> FileOwner | None:
        """Return the unique domain owner, or None when no owner references it."""

        owners = await self.repository.get_owners_by_file_id(file_id)
        unique_owners = {
            (owner.owner_type, owner.owner_id): owner
            for owner in owners
        }

        if not unique_owners:
            return None

        if len(unique_owners) > 1:
            raise AmbiguousFileOwnershipError(file_id)

        return next(iter(unique_owners.values()))
