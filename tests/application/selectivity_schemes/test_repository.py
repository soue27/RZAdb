from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.selectivity_schemes.repository import (
    SelectivitySchemeRepository,
)
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)


@pytest.mark.asyncio
async def test_get_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    scheme_id = uuid7()
    scheme = SelectivityScheme(
        id=scheme_id,
        substation_id=uuid7(),
    )

    session.get.return_value = scheme

    repository = SelectivitySchemeRepository(session)

    result = await repository.get_by_id(scheme_id)

    assert result is scheme
    session.get.assert_awaited_once_with(
        SelectivityScheme,
        scheme_id,
    )


@pytest.mark.asyncio
async def test_get_by_substation_id():
    session = MagicMock()
    session.scalar = AsyncMock()

    substation_id = uuid7()
    scheme = SelectivityScheme(
        id=uuid7(),
        substation_id=substation_id,
    )

    session.scalar.return_value = scheme

    repository = SelectivitySchemeRepository(session)

    result = await repository.get_by_substation_id(substation_id)

    assert result is scheme
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_version_by_id():
    session = MagicMock()
    session.get = AsyncMock()

    version_id = uuid7()
    version = MagicMock(spec=SelectivitySchemeVersion)

    session.get.return_value = version

    repository = SelectivitySchemeRepository(session)

    result = await repository.get_version_by_id(version_id)

    assert result is version
    session.get.assert_awaited_once_with(
        SelectivitySchemeVersion,
        version_id,
    )


@pytest.mark.asyncio
async def test_add_scheme():
    session = MagicMock()
    session.flush = AsyncMock()

    scheme = SelectivityScheme(
        id=uuid7(),
        substation_id=uuid7(),
    )

    repository = SelectivitySchemeRepository(session)

    result = await repository.add_scheme(scheme)

    assert result is scheme
    session.add.assert_called_once_with(scheme)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_version():
    session = MagicMock()
    session.flush = AsyncMock()

    version = MagicMock(spec=SelectivitySchemeVersion)

    repository = SelectivitySchemeRepository(session)

    result = await repository.add_version(version)

    assert result is version
    session.add.assert_called_once_with(version)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_version():
    session = MagicMock()
    session.scalar = AsyncMock()

    scheme_id = uuid7()
    version = MagicMock(spec=SelectivitySchemeVersion)

    session.scalar.return_value = version

    repository = SelectivitySchemeRepository(session)

    result = await repository.get_current_version(scheme_id)

    assert result is version
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_versions():
    session = MagicMock()
    session.scalars = AsyncMock()

    scheme_id = uuid7()
    versions = [
        MagicMock(spec=SelectivitySchemeVersion),
        MagicMock(spec=SelectivitySchemeVersion),
    ]

    scalars_result = MagicMock()
    scalars_result.__iter__.return_value = iter(versions)
    session.scalars.return_value = scalars_result

    repository = SelectivitySchemeRepository(session)

    result = await repository.get_versions(scheme_id)

    assert result == versions
    session.scalars.assert_awaited_once()