from uuid import uuid4

import pytest

from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


@pytest.mark.asyncio
async def test_database_transaction_is_rolled_back(db_session, system_user_id) -> None:
    enterprise = Enterprise(
        id=uuid4(),
        type=EnterpriseType.DEPARTMENT,
        full_name="Rollback Test Department",
        short_name="Rollback Test",
        created_by=system_user_id,
        updated_by=system_user_id,
    )

    db_session.add(enterprise)
    await db_session.flush()

    saved_id = enterprise.id

    result = await db_session.get(Enterprise, saved_id)

    assert result is not None
    assert result.full_name == "Rollback Test Department"
