from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.application.objects.owner_lock import lock_owner_row
from app.domain.substation import Substation


@pytest.mark.asyncio
async def test_owner_lock_uses_for_update_and_refreshes_identity_map() -> None:
    owner_id = uuid4()
    owner = SimpleNamespace(id=owner_id)
    result = SimpleNamespace(one_or_none=lambda: owner)
    session = SimpleNamespace(scalars=AsyncMock(return_value=result))

    locked = await lock_owner_row(session, Substation, owner_id)

    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert locked is owner
    assert "FOR UPDATE" in sql
    assert statement.get_execution_options()["populate_existing"] is True
