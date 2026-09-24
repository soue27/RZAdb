
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.otd.repository import OTDRepository
from app.domain.enums import OTDPurpose
from app.domain.otd import OTD, OTDVersion


@pytest.mark.asyncio
async def test_get_by_id_returns_otd() -> None:
    session = AsyncMock()

    otd = OTD(
        id=uuid7(),
        urza_id=uuid7(),
    )

    session.get.return_value = otd

    repository = OTDRepository(session)

    result = await repository.get_by_id(otd.id)

    assert result is otd
    session.get.assert_awaited_once_with(OTD, otd.id)

@pytest.mark.asyncio
async def test_get_by_urza_id_returns_otd() -> None:
    session = AsyncMock()

    urza_id = uuid7()
    otd = OTD(
        id=uuid7(),
        urza_id=urza_id,
    )

    session.scalar.return_value = otd

    repository = OTDRepository(session)

    result = await repository.get_by_urza_id(urza_id)

    assert result is otd
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_version_by_id_returns_version() -> None:
    session = AsyncMock()

    version = OTDVersion(
        id=uuid7(),
        otd_id=uuid7(),
        version_number=1,
        effective_date=date.today(),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    session.get.return_value = version

    repository = OTDRepository(session)

    result = await repository.get_version_by_id(version.id)

    assert result is version
    session.get.assert_awaited_once_with(OTDVersion, version.id)

@pytest.mark.asyncio
async def test_add_otd() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    otd = OTD(
        id=uuid7(),
        urza_id=uuid7(),
    )

    repository = OTDRepository(session)

    result = await repository.add(otd)

    assert result is otd
    session.add.assert_called_once_with(otd)
    session.flush.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_otd_version() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    version = OTDVersion(
        id=uuid7(),
        otd_id=uuid7(),
        version_number=1,
        effective_date=date.today(),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    repository = OTDRepository(session)

    result = await repository.add_version(version)

    assert result is version
    session.add.assert_called_once_with(version)
    session.flush.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_current_version_returns_latest_version() -> None:
    session = AsyncMock()

    otd_id = uuid7()

    version = OTDVersion(
        id=uuid7(),
        otd_id=otd_id,
        version_number=3,
        effective_date=date.today(),
        urza_service_life=10,
        urza_purpose=OTDPurpose.RZA,
    )

    session.scalar.return_value = version

    repository = OTDRepository(session)

    result = await repository.get_current_version(otd_id)

    assert result is version
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_versions_returns_versions_in_descending_order() -> None:
    session = AsyncMock()

    otd_id = uuid7()

    versions = [
        OTDVersion(
            id=uuid7(),
            otd_id=otd_id,
            version_number=3,
            effective_date=date.today(),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        ),
        OTDVersion(
            id=uuid7(),
            otd_id=otd_id,
            version_number=2,
            effective_date=date.today(),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        ),
        OTDVersion(
            id=uuid7(),
            otd_id=otd_id,
            version_number=1,
            effective_date=date.today(),
            urza_service_life=10,
            urza_purpose=OTDPurpose.RZA,
        ),
    ]

    scalar_result = MagicMock()
    scalar_result.all.return_value = versions
    session.scalars.return_value = scalar_result

    repository = OTDRepository(session)

    result = await repository.get_versions(otd_id)

    assert result == versions
    assert [version.version_number for version in result] == [3, 2, 1]
    session.scalars.assert_awaited_once()
