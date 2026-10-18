from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectNotFoundError
from app.application.urzas.schemas import URZACreate, URZADetails
from app.application.urzas.service import URZAService, URZANameConflictError
from app.domain.enums import ElementBase, RoomCategory, URZACategory, URZAStatus
from app.domain.urza import URZA


@pytest.mark.asyncio
async def test_get_details_returns_urza_details(system_user_id) -> None:
    repository = AsyncMock()

    connection = MagicMock()
    connection.id = uuid7()
    connection.dispatch_name = "ВЛ 110 кВ"

    substation = MagicMock()
    substation.id = uuid7()
    substation.dispatch_name = "ПС Центральная"

    connection.substation = substation

    urza = URZA(
        id=uuid7(),
        connection_id=uuid7(),
        dispatch_name="РЗА-1",
        rdu_subordination=True,
        inventory_number="INV-001",
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    urza.connection = connection

    repository.get_by_id.return_value = urza

    service = URZAService(repository)

    result = await service.get_details(urza.id)

    assert isinstance(result, URZADetails)
    assert result.id == urza.id
    assert result.dispatch_name == "РЗА-1"
    assert result.rdu_subordination is True
    assert result.inventory_number == "INV-001"
    assert result.commissioning_date == date(2020, 1, 1)
    assert result.status is URZAStatus.IN_OPERATION
    assert result.element_base is ElementBase.MICROPROCESSOR
    assert result.category is URZACategory.II
    assert result.room_category is RoomCategory.I
    assert result.complexity is False
    assert result.connection.id == connection.id
    assert result.connection.dispatch_name == "ВЛ 110 кВ"
    assert result.substation.id == substation.id
    assert result.substation.dispatch_name == "ПС Центральная"

    repository.get_by_id.assert_awaited_once_with(urza.id)


@pytest.mark.asyncio
async def test_get_details_raises_when_urza_not_found() -> None:
    repository = AsyncMock()
    repository.get_by_id.return_value = None

    service = URZAService(repository)

    urza_id = uuid7()

    with pytest.raises(ObjectNotFoundError):
        await service.get_details(urza_id)

    repository.get_by_id.assert_awaited_once_with(urza_id)



@pytest.mark.asyncio
async def test_create_urza_sets_fields_and_audit_users(system_user_id) -> None:
    repository = AsyncMock()
    service = URZAService(repository)

    connection_id = uuid7()
    urza_id = uuid7()

    connection = MagicMock()
    connection.id = connection_id
    connection.dispatch_name = "ВЛ 110 кВ"

    substation = MagicMock()
    substation.id = uuid7()
    substation.dispatch_name = "ПС Центральная"

    connection.substation = substation

    repository.exists_by_name.return_value = False

    data = URZACreate(
        dispatch_name="РЗА-2",
        rdu_subordination=True,
        inventory_number="INV-002",
        commissioning_date=date(2026, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
    )

    async def add_urza(urza: URZA) -> URZA:
        urza.id = urza_id
        urza.connection = connection
        return urza

    async def get_urza(requested_id):
        urza = repository.add.await_args.args[0]
        return urza if urza.id == requested_id else None

    repository.add.side_effect = add_urza
    repository.get_by_id.side_effect = get_urza

    result = await service.create(
        connection_id=connection_id,
        actor_id=system_user_id,
        data=data,
    )

    created = repository.add.await_args.args[0]

    assert created.connection_id == connection_id
    assert created.dispatch_name == "РЗА-2"
    assert created.inventory_number == "INV-002"
    assert created.created_by == system_user_id
    assert created.updated_by == system_user_id
    assert result.id == urza_id
    assert result.dispatch_name == "РЗА-2"

    repository.add.assert_awaited_once()
    repository.get_by_id.assert_awaited_once_with(urza_id)



@pytest.mark.asyncio
async def test_update_urza_updates_fields_and_audit_user(system_user_id) -> None:
    repository = AsyncMock()
    service = URZAService(repository)

    urza_id = uuid7()
    connection = MagicMock()
    connection.id = uuid7()
    connection.dispatch_name = "ВЛ 110 кВ"

    substation = MagicMock()
    substation.id = uuid7()
    substation.dispatch_name = "ПС Центральная"
    connection.substation = substation

    urza = URZA(
        id=urza_id,
        connection_id=connection.id,
        dispatch_name="РЗА-1",
        rdu_subordination=False,
        inventory_number="OLD-001",
        commissioning_date=date(2020, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
        created_by=system_user_id,
        updated_by=system_user_id,
    )
    urza.connection = connection
    repository.get_by_id.return_value = urza
    repository.exists_by_name.return_value = False

    data = URZACreate(
        dispatch_name="РЗА-2",
        rdu_subordination=True,
        inventory_number="NEW-002",
        commissioning_date=date(2026, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.III,
        room_category=RoomCategory.II,
        complexity=True,
    )

    result = await service.update(
        urza_id=urza_id,
        actor_id=system_user_id,
        data=data,
    )

    assert urza.dispatch_name == "РЗА-2"
    assert urza.rdu_subordination is True
    assert urza.inventory_number == "NEW-002"
    assert urza.commissioning_date == date(2026, 1, 1)
    assert urza.category is URZACategory.III
    assert urza.room_category is RoomCategory.II
    assert urza.complexity is True
    assert urza.connection_id == connection.id
    assert urza.updated_by == system_user_id
    assert result.dispatch_name == "РЗА-2"

    repository.exists_by_name.assert_awaited_once_with(
        connection.id,
        "РЗА-2",
        exclude_id=urza_id,
    )
    repository.update.assert_awaited_once_with(urza)


@pytest.mark.asyncio
async def test_update_urza_raises_on_name_conflict(system_user_id) -> None:
    repository = AsyncMock()
    service = URZAService(repository)

    urza = MagicMock()
    urza.id = uuid7()
    urza.connection_id = uuid7()
    repository.get_by_id.return_value = urza
    repository.exists_by_name.return_value = True

    data = URZACreate(
        dispatch_name="РЗА-2",
        rdu_subordination=True,
        inventory_number=None,
        commissioning_date=date(2026, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.II,
        room_category=RoomCategory.I,
        complexity=False,
    )

    with pytest.raises(URZANameConflictError):
        await service.update(
            urza_id=urza.id,
            actor_id=system_user_id,
            data=data,
        )

    repository.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_urza_raises_when_not_found(system_user_id) -> None:
    repository = AsyncMock()
    repository.get_by_id.return_value = None
    service = URZAService(repository)

    with pytest.raises(ObjectNotFoundError):
        await service.update(
            urza_id=uuid7(),
            actor_id=system_user_id,
            data=URZACreate(
                dispatch_name="РЗА-2",
                rdu_subordination=True,
                inventory_number=None,
                commissioning_date=date(2026, 1, 1),
                status=URZAStatus.IN_OPERATION,
                element_base=ElementBase.MICROPROCESSOR,
                category=URZACategory.II,
                room_category=RoomCategory.I,
                complexity=False,
            ),
        )

    repository.update.assert_not_awaited()
