from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.application.access.service import AccessService
from app.application.files.access_service import FileAccessService
from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.owners import FileAccessTargetType, FileOwner, FileOwnerType
from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.domain.enums import AccessCategory, UserRole
from app.domain.file import File
from app.domain.user import User
from app.infrastructure.storage.base import ObjectStorage
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_access_service,
    get_file_service,
)
from app.infrastructure.database.session import get_session


@pytest.fixture
def authenticated_client(system_user_id: UUID) -> Iterator[TestClient]:
    current_user = User(
        id=system_user_id,
        full_name="SYSTEM",
        role=UserRole.SUPERADMIN,
        email="system@rzadb.local",
        password_hash="test-hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def file_routes(system_user_id: UUID) -> AsyncIterator[dict]:
    user = User(
        id=system_user_id,
        full_name="SYSTEM",
        role=UserRole.SUPERADMIN,
        email="system@rzadb.local",
        password_hash="test-hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    file = File(
        id=uuid4(),
        s3_key="files/test/route-test.pdf",
        original_name="scan.pdf",
        display_name="Скан",
        extension=".pdf",
        size=16,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    file_repository = MagicMock(spec=FileRepository)
    file_repository.get_by_id = AsyncMock(return_value=file)

    owner_resolver = MagicMock(spec=FileOwnerResolver)
    owner = FileOwner(
        owner_type=FileOwnerType.PROGRAM,
        owner_id=uuid4(),
        access_target_type=FileAccessTargetType.URZA,
        access_target_id=uuid4(),
    )
    owner_resolver.resolve = AsyncMock(return_value=owner)

    access_service = MagicMock(spec=AccessService)
    access_service.can_access_urza = AsyncMock(return_value=True)
    access_service.can_access_substation = AsyncMock(return_value=True)
    file_access_service = FileAccessService(
        file_repository=file_repository,
        owner_resolver=owner_resolver,
        access_service=access_service,
    )

    storage = MagicMock(spec=ObjectStorage)
    storage.download = AsyncMock(return_value=b"test pdf content")
    file_service = FileService(
        repository=file_repository,
        storage=storage,
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_file_access_service] = (
        lambda: file_access_service
    )
    app.dependency_overrides[get_file_service] = lambda: file_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield {
            "client": client,
            "user": user,
            "file": file,
            "file_repository": file_repository,
            "owner_resolver": owner_resolver,
            "owner": owner,
            "access_service": access_service,
            "file_access_service": file_access_service,
            "file_service": file_service,
            "storage": storage,
        }

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_file_access_service, None)
    app.dependency_overrides.pop(get_file_service, None)


def test_upload_file(authenticated_client: TestClient) -> None:
    client = authenticated_client

    content = b"test pdf content"

    response = client.post(
        "/files",
        files={
            "file": (
                "scan.pdf",
                content,
                "application/pdf",
            ),
        },
        data={
            "display_name": "ПС Тестовая — ТО — 2026-09-19",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["original_name"] == "scan.pdf"
    assert data["display_name"] == "ПС Тестовая — ТО — 2026-09-19"
    assert data["extension"] == ".pdf"
    assert data["size"] == len(content)
    assert data["mime_type"] == "application/pdf"
    assert "id" in data
    assert "uploaded_at" in data
    assert "s3_key" not in data


def test_upload_file_without_file(authenticated_client: TestClient) -> None:
    client = authenticated_client

    response = client.post(
        "/files",
        data={
            "display_name": "ПС Тестовая",
        },
    )

    assert response.status_code == 422


def test_upload_file_without_display_name(authenticated_client: TestClient) -> None:
    client = authenticated_client

    response = client.post(
        "/files",
        files={
            "file": (
                "scan.pdf",
                b"test pdf content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "target_type", "access_method", "target_argument", "disposition"),
    [
        ("view", FileAccessTargetType.URZA, "can_access_urza", "urza_id", "inline"),
        ("download", FileAccessTargetType.URZA, "can_access_urza", "urza_id", "attachment"),
        (
            "view",
            FileAccessTargetType.SUBSTATION,
            "can_access_substation",
            "substation_id",
            "inline",
        ),
        (
            "download",
            FileAccessTargetType.SUBSTATION,
            "can_access_substation",
            "substation_id",
            "attachment",
        ),
    ],
)
async def test_file_endpoints_authorize_before_read_and_preserve_response(
    file_routes,
    endpoint,
    target_type,
    access_method,
    target_argument,
    disposition,
) -> None:
    state = file_routes
    owner = FileOwner(
        owner_type=FileOwnerType.PROGRAM,
        owner_id=uuid4(),
        access_target_type=target_type,
        access_target_id=uuid4(),
    )
    state["owner"] = owner
    state["owner_resolver"].resolve.return_value = owner
    getattr(state["access_service"], access_method).return_value = True

    response = await state["client"].get(
        f"/files/{state['file'].id}/{endpoint}",
    )

    assert response.status_code == 200
    assert response.content == b"test pdf content"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'{disposition}; '
        f'filename="{state["file"].original_name}"; '
        f"filename*=UTF-8''{quote(state['file'].original_name)}"
    )
    getattr(state["access_service"], access_method).assert_awaited_once_with(
        user_id=state["user"].id,
        **{target_argument: owner.access_target_id},
    )
    state["file_service"].storage.download.assert_awaited_once_with(
        key=state["file"].s3_key,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["view", "download"])
async def test_anonymous_file_access_returns_401_without_storage_read(
    file_routes,
    endpoint,
) -> None:
    state = file_routes
    app.dependency_overrides.pop(get_current_user)

    async def fake_session():
        yield MagicMock()

    app.dependency_overrides[get_session] = fake_session
    try:
        response = await state["client"].get(
            f"/files/{state['file'].id}/{endpoint}",
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401
    state["owner_resolver"].resolve.assert_not_awaited()
    state["access_service"].can_access_urza.assert_not_awaited()
    state["access_service"].can_access_substation.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["view", "download"])
async def test_denied_file_access_returns_403_without_storage_read(
    file_routes,
    endpoint,
) -> None:
    state = file_routes
    state["access_service"].can_access_urza.return_value = False
    state["file_service"].read = AsyncMock(wraps=state["file_service"].read)

    response = await state["client"].get(
        f"/files/{state['file'].id}/{endpoint}",
    )

    assert response.status_code == 403
    state["file_service"].read.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["view", "download"])
async def test_missing_file_returns_404_without_storage_read(
    file_routes,
    endpoint,
) -> None:
    state = file_routes
    state["file_repository"].get_by_id.return_value = None

    response = await state["client"].get(
        f"/files/{uuid4()}/{endpoint}",
    )

    assert response.status_code == 404
    state["owner_resolver"].resolve.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["view", "download"])
async def test_orphan_file_returns_404_without_storage_read(
    file_routes,
    endpoint,
) -> None:
    state = file_routes
    state["owner_resolver"].resolve.return_value = None

    response = await state["client"].get(
        f"/files/{state['file'].id}/{endpoint}",
    )

    assert response.status_code == 404
    state["access_service"].can_access_urza.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["view", "download"])
async def test_archived_file_returns_403_without_storage_read(
    file_routes,
    endpoint,
) -> None:
    state = file_routes
    state["file"].deleted_at = datetime.now(UTC)

    response = await state["client"].get(
        f"/files/{state['file'].id}/{endpoint}",
    )

    assert response.status_code == 403
    state["owner_resolver"].resolve.assert_not_awaited()
    state["access_service"].can_access_urza.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_type", "access_method"),
    [
        (FileAccessTargetType.URZA, "can_access_urza"),
        (FileAccessTargetType.SUBSTATION, "can_access_substation"),
    ],
)
async def test_archived_domain_owner_can_still_read_file(
    file_routes,
    target_type,
    access_method,
) -> None:
    state = file_routes
    # Owner archive state is intentionally not part of FileOwner; AccessService
    # decides access to the resolved domain target.
    state["owner_resolver"].resolve.return_value = SimpleNamespace(
        owner_type=FileOwnerType.PROGRAM,
        owner_id=uuid4(),
        access_target_type=target_type,
        access_target_id=uuid4(),
        deleted_at=datetime.now(UTC),
    )
    getattr(state["access_service"], access_method).return_value = True

    response = await state["client"].get(
        f"/files/{state['file'].id}/view",
    )

    assert response.status_code == 200
    getattr(state["access_service"], access_method).assert_awaited_once()
    state["file_service"].storage.download.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("debug", [False, True])
async def test_ambiguous_owner_returns_safe_internal_error_without_storage_read(
    file_routes,
    caplog,
    debug,
) -> None:
    state = file_routes
    internal_detail = f"ambiguous owner {state['file'].id} SECRET_OWNER_ID"
    state["owner_resolver"].resolve.side_effect = AmbiguousFileOwnershipError(
        internal_detail,
    )

    original_debug = app.debug
    app.debug = debug
    try:
        response = await state["client"].get(
            f"/files/{state['file'].id}/view",
        )
    finally:
        app.debug = original_debug

    assert response.status_code == 500
    assert response.json() == {"detail": "Внутренняя ошибка сервера."}
    assert internal_detail not in response.text
    assert str(state["file"].id) not in response.text
    assert "SECRET_OWNER_ID" not in response.text
    assert "Traceback" not in response.text
    assert any(
        record.getMessage()
        == "Ambiguous ownership detected while accessing a file."
        and record.exc_info is not None
        for record in caplog.records
    )
    state["access_service"].can_access_urza.assert_not_awaited()
    state["file_service"].storage.download.assert_not_awaited()
