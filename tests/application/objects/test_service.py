from uuid import UUID

import pytest
from uuid6 import uuid7

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.schemas import SelectedObject
from app.application.objects.service import ObjectService


class FakeAccessService:
    def __init__(
        self,
        *,
        substation_access: bool = False,
        connection_access: bool = False,
        urza_access: bool = False,
    ) -> None:
        self.substation_access = substation_access
        self.connection_access = connection_access
        self.urza_access = urza_access

    async def can_access_substation(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> bool:
        return self.substation_access

    async def can_access_connection(
        self,
        user_id: UUID,
        connection_id: UUID,
    ) -> bool:
        return self.connection_access

    async def can_access_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> bool:
        return self.urza_access


class FakeObjectResolver:
    def __init__(self, result: SelectedObject | None) -> None:
        self.result = result

    async def resolve(
        self,
        object_type: str,
        object_id: UUID,
    ) -> SelectedObject | None:
        return self.result


def make_service(
    *,
    access: FakeAccessService,
    result: SelectedObject | None,
) -> ObjectService:
    return ObjectService(
        access_service=access,
        object_resolver=FakeObjectResolver(result),
    )


@pytest.mark.asyncio
async def test_returns_substation_when_user_has_access() -> None:
    user_id = uuid7()
    object_id = uuid7()

    selected_object = SelectedObject(
        object_type="substation",
        id=object_id,
        name="ПС Свердловская",
    )

    service = make_service(
        access=FakeAccessService(substation_access=True),
        result=selected_object,
    )

    result = await service.get_object(
        user_id=user_id,
        object_type="substation",
        object_id=object_id,
    )

    assert result == selected_object


@pytest.mark.asyncio
async def test_raises_access_denied_when_user_has_no_access() -> None:
    service = make_service(
        access=FakeAccessService(substation_access=False),
        result=None,
    )

    with pytest.raises(ObjectAccessDeniedError):
        await service.get_object(
            user_id=uuid7(),
            object_type="substation",
            object_id=uuid7(),
        )


@pytest.mark.asyncio
async def test_returns_connection_when_user_has_access() -> None:
    object_id = uuid7()

    selected_object = SelectedObject(
        object_type="connection",
        id=object_id,
        name="ВЛ 110 кВ Свердловская",
    )

    service = make_service(
        access=FakeAccessService(connection_access=True),
        result=selected_object,
    )

    result = await service.get_object(
        user_id=uuid7(),
        object_type="connection",
        object_id=object_id,
    )

    assert result == selected_object


@pytest.mark.asyncio
async def test_returns_urza_when_user_has_access() -> None:
    object_id = uuid7()

    selected_object = SelectedObject(
        object_type="urza",
        id=object_id,
        name="ДЗЛ-110",
    )

    service = make_service(
        access=FakeAccessService(urza_access=True),
        result=selected_object,
    )

    result = await service.get_object(
        user_id=uuid7(),
        object_type="urza",
        object_id=object_id,
    )

    assert result == selected_object


@pytest.mark.asyncio
async def test_raises_not_found_for_unknown_object_type() -> None:
    service = make_service(
        access=FakeAccessService(),
        result=None,
    )

    with pytest.raises(ObjectNotFoundError):
        await service.get_object(
            user_id=uuid7(),
            object_type="unknown",
            object_id=uuid7(),
        )

@pytest.mark.asyncio
async def test_raises_not_found_when_object_does_not_exist() -> None:
    service = make_service(
        access=FakeAccessService(substation_access=True),
        result=None,
    )

    with pytest.raises(ObjectNotFoundError):
        await service.get_object(
            user_id=uuid7(),
            object_type="substation",
            object_id=uuid7(),
        )