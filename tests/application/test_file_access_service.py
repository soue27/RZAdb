from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.access.service import AccessService
from app.application.files.access_service import FileAccessService
from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.owners import FileAccessTargetType, FileOwner, FileOwnerType
from app.application.files.repository import FileRepository
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.file import File


@pytest.fixture
def file_repository():
    return MagicMock(spec=FileRepository, get_by_id=AsyncMock())


@pytest.fixture
def owner_resolver():
    return MagicMock(spec=FileOwnerResolver, resolve=AsyncMock())


@pytest.fixture
def access_service():
    service = MagicMock(spec=AccessService)
    service.can_access_urza = AsyncMock()
    service.can_access_substation = AsyncMock()
    return service


@pytest.fixture
def service(file_repository, owner_resolver, access_service):
    return FileAccessService(
        file_repository=file_repository,
        owner_resolver=owner_resolver,
        access_service=access_service,
    )


def make_file(*, archived: bool = False) -> File:
    file = MagicMock(spec=File)
    file.deleted_at = datetime.now(UTC) if archived else None
    return file


def make_owner(target_type: FileAccessTargetType) -> FileOwner:
    return FileOwner(
        owner_type=FileOwnerType.PROGRAM,
        owner_id=uuid4(),
        access_target_type=target_type,
        access_target_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_missing_file_raises_not_found(
    service,
    file_repository,
    owner_resolver,
    access_service,
) -> None:
    file_id = uuid4()
    file_repository.get_by_id.return_value = None

    with pytest.raises(ObjectNotFoundError):
        await service.get_accessible_file(uuid4(), file_id)

    owner_resolver.resolve.assert_not_awaited()
    access_service.can_access_urza.assert_not_awaited()
    access_service.can_access_substation.assert_not_awaited()


@pytest.mark.asyncio
async def test_orphan_file_raises_not_found(
    service,
    file_repository,
    owner_resolver,
    access_service,
) -> None:
    file_id = uuid4()
    file = make_file()
    file_repository.get_by_id.return_value = file
    owner_resolver.resolve.return_value = None

    with pytest.raises(ObjectNotFoundError):
        await service.get_accessible_file(uuid4(), file_id)

    owner_resolver.resolve.assert_awaited_once_with(file_id)
    access_service.can_access_urza.assert_not_awaited()
    access_service.can_access_substation.assert_not_awaited()


@pytest.mark.asyncio
async def test_archived_file_is_denied_before_owner_or_access_checks(
    service,
    file_repository,
    owner_resolver,
    access_service,
) -> None:
    file_repository.get_by_id.return_value = make_file(archived=True)

    with pytest.raises(ObjectAccessDeniedError):
        await service.get_accessible_file(uuid4(), uuid4())

    owner_resolver.resolve.assert_not_awaited()
    access_service.can_access_urza.assert_not_awaited()
    access_service.can_access_substation.assert_not_awaited()
    assert not hasattr(service, "storage")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_type", "method_name", "id_argument"),
    [
        (
            FileAccessTargetType.URZA,
            "can_access_urza",
            "urza_id",
        ),
        (
            FileAccessTargetType.SUBSTATION,
            "can_access_substation",
            "substation_id",
        ),
    ],
)
async def test_accessible_owner_returns_file_and_calls_access_service(
    service,
    file_repository,
    owner_resolver,
    access_service,
    target_type,
    method_name,
    id_argument,
) -> None:
    user_id, file_id = uuid4(), uuid4()
    file = make_file()
    owner = make_owner(target_type)
    file_repository.get_by_id.return_value = file
    owner_resolver.resolve.return_value = owner
    getattr(access_service, method_name).return_value = True

    result = await service.get_accessible_file(user_id, file_id)

    assert result is file
    file_repository.get_by_id.assert_awaited_once_with(file_id)
    owner_resolver.resolve.assert_awaited_once_with(file_id)
    getattr(access_service, method_name).assert_awaited_once_with(
        user_id=user_id,
        **{id_argument: owner.access_target_id},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_type", "method_name", "id_argument"),
    [
        (
            FileAccessTargetType.URZA,
            "can_access_urza",
            "urza_id",
        ),
        (
            FileAccessTargetType.SUBSTATION,
            "can_access_substation",
            "substation_id",
        ),
    ],
)
async def test_denied_owner_raises_access_denied(
    service,
    file_repository,
    owner_resolver,
    access_service,
    target_type,
    method_name,
    id_argument,
) -> None:
    user_id, file_id = uuid4(), uuid4()
    file_repository.get_by_id.return_value = make_file()
    owner = make_owner(target_type)
    owner_resolver.resolve.return_value = owner
    getattr(access_service, method_name).return_value = False

    with pytest.raises(ObjectAccessDeniedError):
        await service.get_accessible_file(user_id, file_id)

    getattr(access_service, method_name).assert_awaited_once_with(
        user_id=user_id,
        **{id_argument: owner.access_target_id},
    )
    assert not hasattr(service, "storage")


@pytest.mark.asyncio
async def test_ambiguous_owner_error_is_propagated_without_authorization(
    service,
    file_repository,
    owner_resolver,
    access_service,
) -> None:
    file_id = uuid4()
    file_repository.get_by_id.return_value = make_file()
    owner_resolver.resolve.side_effect = AmbiguousFileOwnershipError(file_id)

    with pytest.raises(AmbiguousFileOwnershipError):
        await service.get_accessible_file(uuid4(), file_id)

    access_service.can_access_urza.assert_not_awaited()
    access_service.can_access_substation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type", list(FileAccessTargetType))
async def test_archived_domain_owner_is_delegated_to_access_service(
    service,
    file_repository,
    owner_resolver,
    access_service,
    target_type,
) -> None:
    """Resolver target IDs are checked regardless of domain archive state."""
    user_id, file_id = uuid4(), uuid4()
    file = make_file()
    owner = make_owner(target_type)
    file_repository.get_by_id.return_value = file
    owner_resolver.resolve.return_value = owner

    if target_type is FileAccessTargetType.URZA:
        access_service.can_access_urza.return_value = True
    else:
        access_service.can_access_substation.return_value = True

    assert await service.get_accessible_file(user_id, file_id) is file
    owner_resolver.resolve.assert_awaited_once_with(file_id)
