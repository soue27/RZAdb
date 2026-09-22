from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_substation = AsyncMock()
    return service


@pytest.fixture
def service(repository, access_service):
    return SelectivitySchemeService(
        repository=repository,
        access_service=access_service,
    )


@pytest.mark.asyncio
async def test_get_by_substation_returns_scheme(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    scheme = SelectivityScheme(
        id=uuid7(),
        substation_id=substation_id,
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=scheme,
    )

    result = await service.get_by_substation(
        user_id,
        substation_id,
    )

    assert result is scheme
    access_service.can_access_substation.assert_awaited_once_with(
        user_id,
        substation_id,
    )
    repository.get_by_substation_id.assert_awaited_once_with(
        substation_id,
    )


@pytest.mark.asyncio
async def test_get_by_substation_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    access_service.can_access_substation.return_value = False
    repository.get_by_substation_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_substation(
            user_id,
            substation_id,
        )

    repository.get_by_substation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_scheme_with_first_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(return_value=None)
    repository.add_scheme = AsyncMock()
    repository.add_version = AsyncMock()

    result = await service.create(
        user_id=user_id,
        substation_id=substation_id,
        number="С-110-01",
        name="Схема селективности ПС-1",
        effective_date=date(2026, 9, 17),
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        change_description="Первичное создание",
        change_justification="Ввод подстанции в эксплуатацию",
    )

    assert isinstance(result, SelectivityScheme)
    assert result.substation_id == substation_id

    repository.add_scheme.assert_awaited_once()

    created_scheme = repository.add_scheme.await_args.args[0]

    assert created_scheme.substation_id == substation_id

    repository.add_version.assert_awaited_once()

    created_version = repository.add_version.await_args.args[0]

    assert isinstance(created_version, SelectivitySchemeVersion)
    assert created_version.selectivity_scheme_id == created_scheme.id
    assert created_version.version_number == 1
    assert created_version.number == "С-110-01"
    assert created_version.name == "Схема селективности ПС-1"
    assert created_version.effective_date == date(2026, 9, 17)
    assert created_version.created_by == user_id
    assert created_version.scan_file_id == scan_file_id
    assert created_version.editable_file_id == editable_file_id
    assert created_version.change_description == "Первичное создание"
    assert (
        created_version.change_justification
        == "Ввод подстанции в эксплуатацию"
    )


@pytest.mark.asyncio
async def test_create_scheme_rejects_duplicate(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    existing = SelectivityScheme(
        id=uuid7(),
        substation_id=substation_id,
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=existing,
    )
    repository.add_scheme = AsyncMock()
    repository.add_version = AsyncMock()

    with pytest.raises(
        ValueError,
        match="уже существует",
    ):
        await service.create(
            user_id=user_id,
            substation_id=substation_id,
            number="С-110-01",
            name="Схема селективности ПС-1",
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.add_scheme.assert_not_awaited()
    repository.add_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_scheme_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    access_service.can_access_substation.return_value = False
    repository.get_by_substation_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            substation_id=substation_id,
            number="С-110-01",
            name="Схема селективности ПС-1",
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.get_by_substation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_version(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scheme_id = uuid7()

    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=substation_id,
    )

    version = MagicMock(spec=SelectivitySchemeVersion)

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=scheme,
    )
    repository.get_current_version = AsyncMock(
        return_value=version,
    )

    result = await service.get_current_version(
        user_id,
        substation_id,
    )

    assert result is version
    repository.get_current_version.assert_awaited_once_with(
        scheme_id,
    )


@pytest.mark.asyncio
async def test_get_current_version_without_scheme(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=None,
    )
    repository.get_current_version = AsyncMock()

    result = await service.get_current_version(
        user_id,
        substation_id,
    )

    assert result is None
    repository.get_current_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_version_increments_version_number(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    scheme_id = uuid7()
    substation_id = uuid7()

    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=substation_id,
    )

    current_version = SelectivitySchemeVersion(
        id=uuid7(),
        selectivity_scheme_id=scheme_id,
        version_number=3,
        number="С-110-01",
        name="Схема селективности ПС-1",
        effective_date=date(2026, 8, 1),
        created_by=uuid7(),
        scan_file_id=uuid7(),
    )

    access_service.can_access_substation.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=scheme,
    )
    repository.get_current_version = AsyncMock(
        return_value=current_version,
    )
    repository.add_version = AsyncMock()

    result = await service.create_version(
        user_id=user_id,
        scheme_id=scheme_id,
        number="С-110-02",
        name="Схема селективности ПС-1 после реконструкции",
        effective_date=date(2026, 9, 17),
        scan_file_id=uuid7(),
        change_description="Изменена схема присоединения",
        change_justification="Реконструкция присоединения",
    )

    assert isinstance(result, SelectivitySchemeVersion)
    assert result.selectivity_scheme_id == scheme_id
    assert result.version_number == 4
    assert result.number == "С-110-02"
    assert (
        result.name
        == "Схема селективности ПС-1 после реконструкции"
    )
    assert result.created_by == user_id

    repository.add_version.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_version_without_scheme(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    scheme_id = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=None,
    )
    repository.add_version = AsyncMock()

    with pytest.raises(
        ValueError,
        match="не найдена",
    ):
        await service.create_version(
            user_id=user_id,
            scheme_id=scheme_id,
            number="С-110-01",
            name="Схема селективности",
            effective_date=date(2026, 9, 17),
            scan_file_id=uuid7(),
        )

    repository.add_version.assert_not_awaited()
    access_service.can_access_substation.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_versions_returns_history(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scheme_id = uuid7()

    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=substation_id,
    )

    versions = [
        MagicMock(spec=SelectivitySchemeVersion),
        MagicMock(spec=SelectivitySchemeVersion),
    ]

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=scheme,
    )
    repository.get_versions = AsyncMock(
        return_value=versions,
    )

    result = await service.get_versions(
        user_id,
        substation_id,
    )

    assert result == versions
    repository.get_versions.assert_awaited_once_with(
        scheme_id,
    )


@pytest.mark.asyncio
async def test_get_versions_without_scheme(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=None,
    )
    repository.get_versions = AsyncMock()

    result = await service.get_versions(
        user_id,
        substation_id,
    )

    assert result == []
    repository.get_versions.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_details_returns_dto(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scheme_id = uuid7()
    version_id = uuid7()
    scan_file_id = uuid7()
    editable_file_id = uuid7()

    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=substation_id,
    )

    version = SelectivitySchemeVersion(
        id=version_id,
        selectivity_scheme_id=scheme_id,
        version_number=2,
        number="С-110-02",
        name="Схема селективности ПС-1 после реконструкции",
        effective_date=date(2026, 9, 17),
        change_description="Изменена схема присоединения",
        change_justification="Реконструкция присоединения",
        created_by=user_id,
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
    )

    creator = MagicMock()
    creator.full_name = "Иванов Иван Иванович"

    scan_file = MagicMock()
    scan_file.display_name = "Схема селективности.pdf"

    editable_file = MagicMock()
    editable_file.display_name = "Схема селективности.xlsx"

    version.creator = creator
    version.scan_file = scan_file
    version.editable_file = editable_file

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=scheme,
    )
    repository.get_current_version = AsyncMock(
        return_value=version,
    )

    result = await service.get_details(
        user_id=user_id,
        substation_id=substation_id,
    )

    assert result is not None
    assert result.scheme_id == scheme_id
    assert result.version_id == version_id
    assert result.version_number == 2
    assert result.number == "С-110-02"
    assert result.name == "Схема селективности ПС-1 после реконструкции"
    assert result.effective_date == date(2026, 9, 17)
    assert result.change_description == "Изменена схема присоединения"
    assert result.change_justification == "Реконструкция присоединения"
    assert result.created_by == user_id
    assert result.creator_name == "Иванов Иван Иванович"
    assert result.scan_file_id == scan_file_id
    assert result.scan_file_name == "Схема селективности.pdf"
    assert result.editable_file_id == editable_file_id
    assert result.editable_file_name == "Схема селективности.xlsx"


@pytest.mark.asyncio
async def test_get_version_list_returns_dtos(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    substation_id = uuid7()
    scheme_id = uuid7()

    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=substation_id,
    )

    version_2 = SelectivitySchemeVersion(
        id=uuid7(),
        selectivity_scheme_id=scheme_id,
        version_number=2,
        number="С-110-02",
        name="Схема после реконструкции",
        effective_date=date(2026, 9, 17),
        change_description="Изменена схема присоединения",
        change_justification="Реконструкция",
        created_by=user_id,
        scan_file_id=uuid7(),
        editable_file_id=uuid7(),
    )

    version_1 = SelectivitySchemeVersion(
        id=uuid7(),
        selectivity_scheme_id=scheme_id,
        version_number=1,
        number="С-110-01",
        name="Схема селективности ПС-1",
        effective_date=date(2026, 8, 1),
        change_description="Первичное создание",
        change_justification="Ввод подстанции в эксплуатацию",
        created_by=user_id,
        scan_file_id=uuid7(),
    )

    creator = MagicMock()
    creator.full_name = "Иванов Иван Иванович"

    scan_file_2 = MagicMock()
    scan_file_2.display_name = "Схема v2.pdf"

    editable_file_2 = MagicMock()
    editable_file_2.display_name = "Схема v2.xlsx"

    scan_file_1 = MagicMock()
    scan_file_1.display_name = "Схема v1.pdf"

    version_2.creator = creator
    version_2.scan_file = scan_file_2
    version_2.editable_file = editable_file_2

    version_1.creator = creator
    version_1.scan_file = scan_file_1
    version_1.editable_file = None

    access_service.can_access_substation.return_value = True
    repository.get_by_substation_id = AsyncMock(
        return_value=scheme,
    )
    repository.get_versions = AsyncMock(
        return_value=[version_2, version_1],
    )

    result = await service.get_version_list(
        user_id=user_id,
        substation_id=substation_id,
    )

    assert len(result) == 2

    assert result[0].version_id == version_2.id
    assert result[0].version_number == 2
    assert result[0].number == "С-110-02"
    assert result[0].name == "Схема после реконструкции"
    assert result[0].creator_name == "Иванов Иван Иванович"
    assert result[0].scan_file_name == "Схема v2.pdf"
    assert result[0].editable_file_name == "Схема v2.xlsx"

    assert result[1].version_id == version_1.id
    assert result[1].version_number == 1
    assert result[1].number == "С-110-01"
    assert result[1].name == "Схема селективности ПС-1"
    assert result[1].creator_name == "Иванов Иван Иванович"
    assert result[1].scan_file_name == "Схема v1.pdf"
    assert result[1].editable_file_name is None