from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.urzas.repository import URZARepository
from app.domain.enums import ElementBase, RoomCategory, URZACategory, URZAStatus
from app.domain.urza import URZA
from app.domain.connection import Connection
from app.domain.substation import Substation


@pytest.mark.asyncio
async def test_get_by_id_returns_urza(system_user_id) -> None:
    session = AsyncMock()

    urza = URZA(
        id=uuid7(),
        connection_id=uuid7(),
        dispatch_name="РЗА-1",
        rdu_subordination=False,
        inventory_number=None,
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    scalars_result = MagicMock()
    scalars_result.one_or_none.return_value = urza
    session.scalars.return_value = scalars_result

    repository = URZARepository(session)

    result = await repository.get_by_id(urza.id)

    assert result is urza
    scalars_result.one_or_none.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_id_loads_connection_and_substation() -> None:
    urza_id = uuid7()
    connection_id = uuid7()
    substation_id = uuid7()

    substation = MagicMock(spec=Substation)
    substation.id = substation_id
    substation.dispatch_name = "ПС Центральная"

    connection = MagicMock(spec=Connection)
    connection.id = connection_id
    connection.dispatch_name = "ВЛ 110 кВ"
    connection.substation = substation

    urza = MagicMock(spec=URZA)
    urza.id = urza_id
    urza.connection = connection

    scalars_result = MagicMock()
    scalars_result.one_or_none.return_value = urza

    session = MagicMock()
    session.scalars = AsyncMock(return_value=scalars_result)

    repository = URZARepository(session)

    result = await repository.get_by_id(urza_id)

    assert result is urza
    assert result.connection is connection
    assert result.connection.substation is substation
    assert result.connection.dispatch_name == "ВЛ 110 кВ"
    assert result.connection.substation.dispatch_name == "ПС Центральная"


@pytest.mark.asyncio
async def test_get_by_id_including_deleted_returns_urza_with_relationships(
    system_user_id,
) -> None:
    urza_id = uuid7()
    connection_id = uuid7()
    substation_id = uuid7()

    substation = MagicMock(spec=Substation)
    substation.id = substation_id
    substation.dispatch_name = "ПС Центральная"

    connection = MagicMock(spec=Connection)
    connection.id = connection_id
    connection.dispatch_name = "ВЛ 110 кВ"
    connection.substation = substation

    urza = URZA(
        id=urza_id,
        connection_id=connection_id,
        dispatch_name="Архивное РЗА",
        rdu_subordination=False,
        inventory_number=None,
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    urza.deleted_at = datetime.now(UTC)
    urza.connection = connection

    scalars_result = MagicMock()
    scalars_result.one_or_none.return_value = urza

    session = MagicMock()
    session.scalars = AsyncMock(return_value=scalars_result)

    repository = URZARepository(session)

    result = await repository.get_by_id_including_deleted(urza_id)

    assert result is urza
    assert result.deleted_at is not None
    assert result.connection is connection
    assert result.connection.substation is substation
    assert result.connection.dispatch_name == "ВЛ 110 кВ"
    assert result.connection.substation.dispatch_name == "ПС Центральная"

    query = session.scalars.await_args.args[0]
    assert "urzas.deleted_at IS NULL" not in str(query)
