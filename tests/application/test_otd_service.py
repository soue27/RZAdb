from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from uuid6 import uuid7

from app.application.otd.service import OTDService
from app.domain.enums import OTDPurpose
from app.domain.otd import OTD, OTDVersion


@pytest.mark.asyncio
async def test_get_by_urza_returns_otd_when_access_allowed() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    otd = OTD(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = otd

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_by_urza(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is otd

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_by_urza_id.assert_awaited_once_with(
        urza_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_returns_none_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_by_urza(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is None

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_by_urza_id.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_creates_otd_and_first_version() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = None

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        effective_date=date(2026, 9, 16),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    assert result.urza_id == urza_id

    repository.add.assert_awaited_once()
    repository.add_version.assert_awaited_once()

    created_otd = repository.add.await_args.args[0]
    created_version = repository.add_version.await_args.args[0]

    assert created_otd is result
    assert created_version.otd_id == result.id
    assert created_version.version_number == 1
    assert created_version.effective_date == date(2026, 9, 16)
    assert created_version.urza_service_life == 10
    assert created_version.urza_purpose == OTDPurpose.RZA

@pytest.mark.asyncio
async def test_create_raises_permission_error_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(PermissionError, match="Доступ к URZA запрещён"):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            effective_date=date(2026, 9, 16),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        )

    repository.get_by_urza_id.assert_not_awaited()
    repository.add.assert_not_awaited()
    repository.add_version.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_raises_value_error_when_otd_already_exists() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    existing_otd = OTD(
        id=uuid7(),
        urza_id=urza_id,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = existing_otd

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(
        ValueError,
        match="OTD для данного URZA уже существует",
    ):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            effective_date=date(2026, 9, 16),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        )

    repository.add.assert_not_awaited()
    repository.add_version.assert_not_awaited()

@pytest.mark.asyncio
async def test_get_current_version_returns_version() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    otd = OTD(
        id=uuid7(),
        urza_id=urza_id,
    )

    version = OTDVersion(
        id=uuid7(),
        otd_id=otd.id,
        version_number=2,
        effective_date=date.today(),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = otd
    repository.get_current_version.return_value = version

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_current_version(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is version

    repository.get_by_urza_id.assert_awaited_once_with(urza_id)
    repository.get_current_version.assert_awaited_once_with(otd.id)

@pytest.mark.asyncio
async def test_get_current_version_returns_none_when_otd_not_found() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = None

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_current_version(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is None

    repository.get_current_version.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_version_increments_version_number() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    otd_id = uuid7()

    otd = OTD(
        id=otd_id,
        urza_id=urza_id,
    )

    current_version = OTDVersion(
        id=uuid7(),
        otd_id=otd_id,
        version_number=3,
        effective_date=date(2026, 1, 1),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_id.return_value = otd
    repository.get_current_version.return_value = current_version

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.create_version(
        user_id=user_id,
        otd_id=otd_id,
        effective_date=date(2026, 9, 16),
        urza_service_life=12,
        urza_purpose=OTDPurpose.RZA,
    )

    assert result.otd_id == otd_id
    assert result.version_number == 4
    assert result.effective_date == date(2026, 9, 16)
    assert result.urza_service_life == 12
    assert result.urza_purpose == OTDPurpose.RZA

    repository.add_version.assert_awaited_once()

@pytest.mark.asyncio
async def test_create_version_raises_value_error_when_otd_not_found() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    otd_id = uuid7()

    repository.get_by_id.return_value = None

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(ValueError, match="OTD не найден"):
        await service.create_version(
            user_id=user_id,
            otd_id=otd_id,
            effective_date=date(2026, 9, 16),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        )

    access_service.can_access_urza.assert_not_awaited()
    repository.get_current_version.assert_not_awaited()
    repository.add_version.assert_not_awaited()

@pytest.mark.asyncio
async def test_create_version_raises_permission_error_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    otd_id = uuid7()

    otd = OTD(
        id=otd_id,
        urza_id=urza_id,
    )

    repository.get_by_id.return_value = otd
    access_service.can_access_urza.return_value = False

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    with pytest.raises(PermissionError, match="Доступ к URZA запрещён"):
        await service.create_version(
            user_id=user_id,
            otd_id=otd_id,
            effective_date=date(2026, 9, 16),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        )

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )

    repository.get_current_version.assert_not_awaited()
    repository.add_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_versions_returns_versions() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    otd_id = uuid7()

    otd = OTD(
        id=otd_id,
        urza_id=urza_id,
    )

    versions = [
        OTDVersion(
            id=uuid7(),
            otd_id=otd_id,
            version_number=3,
            effective_date=date(2026, 9, 16),
            urza_service_life=12,
            urza_purpose=OTDPurpose.RZA,
        ),
        OTDVersion(
            id=uuid7(),
            otd_id=otd_id,
            version_number=2,
            effective_date=date(2025, 1, 1),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        ),
    ]

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = otd
    repository.get_versions.return_value = versions

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_versions(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result == versions

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_awaited_once_with(urza_id)
    repository.get_versions.assert_awaited_once_with(otd_id)


@pytest.mark.asyncio
async def test_get_versions_returns_empty_list_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_versions(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result == []

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_not_awaited()
    repository.get_versions.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_details_returns_current_version_and_history() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()
    otd_id = uuid7()

    otd = OTD(
        id=otd_id,
        urza_id=urza_id,
    )

    version_2 = OTDVersion(
        id=uuid7(),
        otd_id=otd_id,
        version_number=2,
        effective_date=date(2026, 1, 1),
        created_at=datetime(2026, 8, 20, 10, 0),
        panel_cabinet_type="Шкаф РЗА",
        terminal_type="МП терминал",
        urza_service_life=12,
        urza_purpose=OTDPurpose.RZA,
    )

    version_1 = OTDVersion(
        id=uuid7(),
        otd_id=otd_id,
        version_number=1,
        effective_date=date(2025, 1, 1),
        created_at=datetime(2025, 3, 15, 10, 0),
        panel_cabinet_type="Шкаф РЗА",
        terminal_type="МП терминал",
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id.return_value = otd
    repository.get_versions.return_value = [version_2, version_1]

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_details(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is not None
    assert result.id == otd_id

    assert result.current_version is not None
    assert result.current_version.id == version_2.id
    assert result.current_version.version_number == 2
    assert result.current_version.urza_service_life == 12
    assert result.current_version.created_at == version_2.created_at

    assert len(result.versions) == 2
    assert result.versions[0].version_number == 2
    assert result.versions[1].version_number == 1
    assert result.versions[0].created_at == version_2.created_at
    assert result.versions[1].created_at == version_1.created_at

    repository.get_by_urza_id.assert_awaited_once_with(urza_id)
    repository.get_versions.assert_awaited_once_with(otd_id)


@pytest.mark.asyncio
async def test_get_details_returns_none_when_access_denied() -> None:
    repository = AsyncMock()
    access_service = AsyncMock()

    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False

    service = OTDService(
        repository=repository,
        access_service=access_service,
    )

    result = await service.get_details(
        user_id=user_id,
        urza_id=urza_id,
    )

    assert result is None

    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_not_awaited()
    repository.get_versions.assert_not_awaited()