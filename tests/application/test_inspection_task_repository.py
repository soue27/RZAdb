from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid6 import uuid7

from app.application.inspections.repository import InspectionTaskRepository
from app.domain.enums import UserRole


@pytest.mark.asyncio
async def test_dashboard_inspection_count_uses_department_scope_and_terminal_statuses():
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    repository = InspectionTaskRepository(session)
    user_id, enterprise_id = uuid7(), uuid7()

    await repository.count_dashboard_statuses(
        user_id=user_id,
        role=UserRole.MANAGER,
        enterprise_ids={enterprise_id},
        now=datetime.now(UTC),
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "GROUP BY inspection_tasks.status" in sql
    assert "inspection_tasks.deleted_at IS NULL" in sql
    assert "substations.enterprise_id IN" in sql
    assert "inspection_tasks.deadline_at" in sql
    assert "closed" in sql and "rejected" in sql
    assert "inspection_history" not in sql
