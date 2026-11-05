from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7
from sqlalchemy.exc import IntegrityError

from app.application.files.service import FileService
from app.application.files.physical_deletion import PhysicalDeletionService, TARGETS
from app.domain.enums import UserRole
from app.domain.file import File

from app.application.files import validation
from app.application.files.validation import (
    FileTooLargeError,
    UnsupportedFileTypeError,
)


class _DeletionSession:
    def __init__(self, *scalar_values, files=()):
        self.scalar_values = iter(scalar_values)
        self.files = list(files)
        self.deleted = []
        self.events = []
        self.rollback_called = False
        self.commit_error = None

    async def scalar(self, _query):
        return next(self.scalar_values)

    async def get(self, _model, _record_id):
        return next(self.scalar_values)

    async def scalars(self, _query):
        return MagicMock(all=lambda: self.files)

    async def delete(self, record):
        self.deleted.append(record)

    async def flush(self):
        self.events.append("flush")

    async def commit(self):
        self.events.append("commit")
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollback_called = True


class _DeletionAccess:
    def __init__(self, role=UserRole.MANAGER, allowed=True):
        self.user_repository = MagicMock()
        self.user_repository.get_by_id = AsyncMock(
            return_value=MagicMock(role=role, active=True, deleted_at=None)
        )
        self.allowed = allowed

    async def can_access_substation(self, *_args):
        return self.allowed

    async def can_access_urza(self, *_args):
        return self.allowed


class _FileOwners:
    def __init__(self, owners=()):
        self.owners = list(owners)

    async def get_owners_by_file_id(self, _file_id):
        return self.owners


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(TARGETS))
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN])
async def test_physical_delete_commits_each_allowed_category(kind, role):
    target = TARGETS[kind]
    parent_field = target.parent_field
    owner_field = target.parent_owner_field
    parent_id = uuid7()
    record_values = {"id": uuid7(), "deleted_at": None}
    if target.scope == "substation_id":
        record_values["substation_id"] = parent_id
        scalar_values = [SimpleNamespace(**record_values)]
    elif target.scope == "urza_id":
        record_values["urza_id"] = parent_id
        scalar_values = [SimpleNamespace(**record_values)]
    else:
        record_values[parent_field] = uuid7()
        record = SimpleNamespace(**record_values)
        parent = SimpleNamespace(id=record_values[parent_field], **{owner_field: parent_id})
        if target.scope == "version":
            scalar_values = [record, parent]
        else:
            scalar_values = [record]
    record = scalar_values[0]
    for column in target.model.__table__.columns:
        if any(fk.target_fullname == "files.id" for fk in column.foreign_keys):
            setattr(record, column.name, None)
    if target.scope == "urza" and target.scope != "version":
        scalar_values.append(parent)

    session = _DeletionSession(*scalar_values)
    storage = MagicMock()
    storage.delete = AsyncMock()
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(role=role),
        file_owners=_FileOwners(),
        storage=storage,
    )

    result = await service.delete(kind=kind, record_id=record.id, user_id=uuid7())

    assert result.owner_id == parent_id
    assert session.deleted == [record]
    assert session.events[-1] == "commit"


@pytest.mark.asyncio
async def test_physical_delete_denies_engineer_before_mutating_record():
    record = SimpleNamespace(id=uuid7(), deleted_at=None, urza_id=uuid7())
    session = _DeletionSession(record)
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(role=UserRole.ENGINEER),
        file_owners=_FileOwners(),
        storage=MagicMock(),
    )

    with pytest.raises(PermissionError):
        await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.deleted == []
    assert session.events == []


@pytest.mark.asyncio
async def test_physical_delete_keeps_file_with_another_owner():
    shared_file = SimpleNamespace(id=uuid7(), s3_key="files/shared.pdf")
    record = SimpleNamespace(
        id=uuid7(), deleted_at=None, urza_id=uuid7(),
        scan_file_id=shared_file.id, editable_file_id=None,
    )
    session = _DeletionSession(record, files=[shared_file])
    storage = MagicMock()
    storage.delete = AsyncMock()
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(),
        file_owners=_FileOwners(owners=[object()]),
        storage=storage,
    )

    await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.deleted == [record]
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_physical_delete_removes_unowned_file_only_after_commit():
    file = SimpleNamespace(id=uuid7(), s3_key="files/unused.pdf")
    record = SimpleNamespace(
        id=uuid7(), deleted_at=None, urza_id=uuid7(),
        scan_file_id=file.id, editable_file_id=None,
    )
    session = _DeletionSession(record, files=[file])
    storage = MagicMock()

    async def delete_object(*, key):
        assert session.events[-1] == "commit"
        assert key == file.s3_key
        session.events.append("storage-delete")

    storage.delete = AsyncMock(side_effect=delete_object)
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(),
        file_owners=_FileOwners(),
        storage=storage,
    )

    await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.deleted == [record, file]
    assert session.events[-2:] == ["commit", "storage-delete"]


@pytest.mark.asyncio
async def test_physical_delete_does_not_remove_file_when_commit_fails():
    file = SimpleNamespace(id=uuid7(), s3_key="files/unused.pdf")
    record = SimpleNamespace(
        id=uuid7(), deleted_at=None, urza_id=uuid7(),
        scan_file_id=file.id, editable_file_id=None,
    )
    session = _DeletionSession(record, files=[file])
    session.commit_error = RuntimeError("commit failed")
    storage = MagicMock()
    storage.delete = AsyncMock()
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(),
        file_owners=_FileOwners(),
        storage=storage,
    )

    with pytest.raises(RuntimeError, match="Не удалось выполнить удаление"):
        await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.rollback_called
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_physical_delete_preserves_integrity_error_type():
    integrity_error = IntegrityError("DELETE", {}, Exception("constraint"))
    record = SimpleNamespace(
        id=uuid7(), deleted_at=None, urza_id=uuid7(),
        scan_file_id=None, editable_file_id=None,
    )
    session = _DeletionSession(record)
    session.commit_error = integrity_error
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(),
        file_owners=_FileOwners(),
        storage=MagicMock(),
    )

    with pytest.raises(IntegrityError) as error:
        await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert error.value is integrity_error
    assert session.rollback_called


@pytest.mark.asyncio
async def test_physical_delete_reports_file_error_after_committing_record():
    file = SimpleNamespace(id=uuid7(), s3_key="files/unused.pdf")
    record = SimpleNamespace(
        id=uuid7(), deleted_at=None, urza_id=uuid7(),
        scan_file_id=file.id, editable_file_id=None,
    )
    session = _DeletionSession(record, files=[file])
    storage = MagicMock()
    storage.delete = AsyncMock(side_effect=OSError("storage unavailable"))
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(),
        file_owners=_FileOwners(),
        storage=storage,
    )

    result = await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.events[-1] == "commit"
    assert result.file_cleanup_failed is True
    storage.delete.assert_awaited_once_with(key=file.s3_key)


@pytest.mark.asyncio
async def test_physical_delete_denies_out_of_scope_object():
    record = SimpleNamespace(id=uuid7(), deleted_at=None, urza_id=uuid7())
    session = _DeletionSession(record)
    service = PhysicalDeletionService(
        session=session,
        access_service=_DeletionAccess(allowed=False),
        file_owners=_FileOwners(),
        storage=MagicMock(),
    )

    with pytest.raises(PermissionError):
        await service.delete(kind="program", record_id=record.id, user_id=uuid7())

    assert session.deleted == []
    assert session.events == []


@pytest.fixture
def repository():
    repository = MagicMock()
    repository.add = AsyncMock()
    return repository


@pytest.fixture
def storage():
    storage = MagicMock()
    storage.upload = AsyncMock()
    storage.delete = AsyncMock()
    return storage


@pytest.fixture
def service(repository, storage):
    return FileService(
        repository=repository,
        storage=storage,
    )


@pytest.mark.asyncio
async def test_upload_file(
    service,
    repository,
    storage,
    system_user_id,
):
    content = b"test file content"

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="scan.pdf",
        display_name="Скан протокола.pdf",
        extension=".pdf",
        mime_type="application/pdf",
    )

    assert isinstance(result, File)
    assert result.original_name == "scan.pdf"
    assert result.display_name == "Скан протокола.pdf"
    assert result.extension == ".pdf"
    assert result.mime_type == "application/pdf"
    assert result.size == len(content)
    assert result.created_by == system_user_id
    assert result.updated_by == system_user_id

    assert result.s3_key.startswith("files/")
    assert result.s3_key.endswith(".pdf")

    storage.upload.assert_awaited_once_with(
        key=result.s3_key,
        content=content,
    )

    repository.add.assert_awaited_once_with(result)
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_deletes_storage_object_when_storage_upload_fails(
    service,
    repository,
    storage,
    system_user_id,
):
    storage.upload.side_effect = OSError("storage upload error")

    with pytest.raises(OSError, match="storage upload error"):
        await service.upload(
            actor_id=system_user_id,
            content=b"test file content",
            original_name="scan.pdf",
            display_name="Скан протокола.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

    key = storage.upload.await_args.kwargs["key"]
    storage.delete.assert_awaited_once_with(key=key)
    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_preserves_storage_upload_error_when_cleanup_fails(
    service,
    repository,
    storage,
    system_user_id,
    caplog,
):
    upload_error = OSError("storage upload error")
    storage.upload.side_effect = upload_error
    storage.delete.side_effect = RuntimeError("storage cleanup error")

    with pytest.raises(OSError) as exc_info:
        await service.upload(
            actor_id=system_user_id,
            content=b"test file content",
            original_name="scan.pdf",
            display_name="Скан протокола.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

    assert exc_info.value is upload_error
    storage.delete.assert_awaited_once_with(
        key=storage.upload.await_args.kwargs["key"],
    )
    repository.add.assert_not_awaited()
    assert any(
        "Не удалось удалить объект после ошибки загрузки"
        in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_upload_deletes_storage_object_when_repository_add_fails(
    service,
    repository,
    storage,
    system_user_id,
):
    repository.add.side_effect = RuntimeError("database error")

    with pytest.raises(RuntimeError, match="database error"):
        await service.upload(
            actor_id=system_user_id,
            content=b"test file content",
            original_name="scan.pdf",
            display_name="Скан протокола.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

    storage.upload.assert_awaited_once()
    storage.delete.assert_awaited_once_with(
        key=storage.upload.await_args.kwargs["key"],
    )


@pytest.mark.asyncio
async def test_upload_preserves_repository_error_when_storage_cleanup_fails(
    service,
    repository,
    storage,
    system_user_id,
):
    repository.add.side_effect = RuntimeError("database error")
    storage.delete.side_effect = OSError("storage cleanup error")

    with pytest.raises(RuntimeError, match="database error"):
        await service.upload(
            actor_id=system_user_id,
            content=b"test file content",
            original_name="scan.pdf",
            display_name="Скан протокола.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

    storage.delete.assert_awaited_once()



@pytest.mark.asyncio
async def test_upload_normalizes_extension(
    service,
    repository,
    storage,
    system_user_id,
):
    content = b"test"

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="scan.PDF",
        display_name="Скан.pdf",
        extension=".PDF",
        mime_type="application/pdf",
    )

    assert result.extension == ".pdf"
    assert result.s3_key.endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_accepts_extension_without_dot(
    service,
    repository,
    storage,
    system_user_id,
):
    content = b"test"

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="scan.pdf",
        display_name="Скан.pdf",
        extension="PDF",
        mime_type="application/pdf",
    )

    assert result.extension == ".pdf"
    assert result.s3_key.endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_stores_exact_content(
    service,
    repository,
    storage,
    system_user_id,
):
    content = b"\x00\x01\x02\x03test"

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="data.pdf",
        display_name="Данные",
        extension=".pdf",
        mime_type="application/pdf",
    )

    storage.upload.assert_awaited_once_with(
        key=result.s3_key,
        content=content,
    )


@pytest.mark.asyncio
async def test_upload_sets_file_size_from_content(
    service,
    repository,
    storage,
    system_user_id,
):
    content = b"123456789"

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="test.pdf",
        display_name="Тест",
        extension=".pdf",
        mime_type="application/pdf",
    )

    assert result.size == 9


@pytest.mark.asyncio
async def test_read_file_returns_binary_and_uses_file_key(
    service,
    repository,
    storage,
    system_user_id,
):
    file = File(
        s3_key="files/2026/09/read-test.pdf",
        original_name="read-test.pdf",
        display_name="Файл для чтения",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    content = b"data"
    storage.download = AsyncMock(return_value=content)
    repository.get_by_id = AsyncMock()

    result = await service.read(file)

    assert result == content
    storage.download.assert_awaited_once_with(key=file.s3_key)
    repository.get_by_id.assert_not_awaited()
    assert not hasattr(service, "access_service")


@pytest.mark.asyncio
async def test_read_file_propagates_storage_error(service, storage, system_user_id):
    file = File(
        s3_key="files/2026/09/missing.pdf",
        original_name="missing.pdf",
        display_name="Отсутствующий файл",
        extension=".pdf",
        size=0,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    storage_error = FileNotFoundError(file.s3_key)
    storage.download = AsyncMock(side_effect=storage_error)

    with pytest.raises(FileNotFoundError) as exc_info:
        await service.read(file)

    assert exc_info.value is storage_error
    storage.download.assert_awaited_once_with(key=file.s3_key)


@pytest.mark.asyncio
async def test_archive_file(service, repository, storage, system_user_id):
    file_id = uuid7()
    user_id = uuid7()

    file = File(
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    file.id = file_id

    repository.get_by_id = AsyncMock(
        return_value=file,
    )
    repository.save = AsyncMock()

    result = await service.archive(
        file_id=file_id,
        user_id=user_id,
    )

    assert result is file
    assert result.deleted_at is not None
    assert result.deleted_by == user_id
    assert result.updated_by == user_id

    repository.get_by_id.assert_awaited_once_with(
        file_id,
    )
    repository.save.assert_awaited_once_with(
        file,
    )
    storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_archive_missing_file(
    service,
    repository,
    storage,
):
    file_id = uuid7()
    user_id = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=None,
    )
    repository.save = AsyncMock()

    with pytest.raises(
        FileNotFoundError,
    ):
        await service.archive(
            file_id=file_id,
            user_id=user_id,
        )

    repository.save.assert_not_awaited()
    storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_archive_already_archived_file(
    service, repository, storage, system_user_id
):
    file_id = uuid7()
    user_id = uuid7()

    file = File(
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    file.id = file_id
    file.deleted_at = datetime.now(UTC)
    file.deleted_by = system_user_id

    repository.get_by_id = AsyncMock(
        return_value=file,
    )
    repository.save = AsyncMock()

    with pytest.raises(
        ValueError,
        match="уже находится в архиве",
    ):
        await service.archive(
            file_id=file_id,
            user_id=user_id,
        )

    repository.save.assert_not_awaited()
    storage.delete.assert_not_called()



@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension_before_storage(
    service,
    repository,
    storage,
    system_user_id,
):
    with pytest.raises(UnsupportedFileTypeError):
        await service.upload(
            actor_id=system_user_id,
            content=b"not allowed",
            original_name="payload.exe",
            display_name="Недопустимый файл",
            extension=".exe",
            mime_type="application/octet-stream",
        )

    storage.upload.assert_not_awaited()
    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_rejects_file_over_size_limit_before_storage(
    service,
    repository,
    storage,
    system_user_id,
    monkeypatch,
):
    monkeypatch.setattr(validation, "MAX_FILE_SIZE_BYTES", 10)

    with pytest.raises(FileTooLargeError):
        await service.upload(
            actor_id=system_user_id,
            content=b"x" * 11,
            original_name="scan.pdf",
            display_name="Скан",
            extension=".pdf",
            mime_type="application/pdf",
        )

    storage.upload.assert_not_awaited()
    repository.add.assert_not_awaited()


@pytest.mark.parametrize("extension", sorted(validation.MIME_TYPES_BY_EXTENSION))
def test_validate_upload_accepts_allowed_extensions(extension):
    assert validation.validate_upload(
        filename=f"document{extension}",
    ) == extension


@pytest.mark.parametrize("extension", [".exe", ".js", ".html", ".zip", ".dwg.exe"])
def test_validate_upload_rejects_disallowed_extensions(extension):
    with pytest.raises(UnsupportedFileTypeError):
        validation.validate_upload(filename=f"drawing{extension}")


@pytest.mark.parametrize(
    "extension",
    [".dwg", ".dxf", ".dgn", ".dwf", ".dwfx", ".plt", ".vsd", ".vsdx",
     ".odg", ".step", ".stp", ".iges", ".igs", ".ifc", ".svg", ".eps"],
)
@pytest.mark.asyncio
async def test_upload_stores_new_drawing_formats_as_generic_binary(
    extension,
    service,
    repository,
    system_user_id,
):
    result = await service.upload(
        actor_id=system_user_id,
        content=b"drawing content",
        original_name=f"drawing{extension}",
        display_name=f"drawing{extension}",
        extension=extension,
        mime_type="application/octet-stream",
    )

    assert result.extension == extension
    assert result.mime_type == "application/octet-stream"
    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_upload_accepts_file_at_size_limit(
    service,
    repository,
    storage,
    system_user_id,
    monkeypatch,
):
    monkeypatch.setattr(validation, "MAX_FILE_SIZE_BYTES", 10)
    content = b"x" * 10

    result = await service.upload(
        actor_id=system_user_id,
        content=content,
        original_name="scan.pdf",
        display_name="Скан",
        extension=".pdf",
        mime_type="application/pdf",
    )

    assert result.size == 10
    storage.upload.assert_awaited_once()
    repository.add.assert_awaited_once_with(result)
