from decimal import Decimal

import pytest

from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    EnterpriseType,
    UserRole,
)
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_user_persistence() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
            sap_code="SAP-DEP-001",
        )

        superadmin = User(
            full_name="Суперадминистратор Тестовый",
            role=UserRole.SUPERADMIN,
            email="superadmin@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.I,
            active=True,
        )

        engineer = User(
            full_name="Инженер Тестовый",
            role=UserRole.ENGINEER,
            email="engineer@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            sap_code="SAP-USER-001",
            active=True,
        )

        session.add_all([superadmin, engineer])
        await session.flush()

        assert superadmin.id is not None
        assert superadmin.enterprise_id is None
        assert superadmin.role == UserRole.SUPERADMIN
        assert superadmin.email == "superadmin@test.local"
        assert superadmin.active is True

        assert engineer.id is not None
        assert engineer.enterprise_id == department.id
        assert engineer.role == UserRole.ENGINEER
        assert engineer.email == "engineer@test.local"
        assert engineer.access_category == AccessCategory.III
        assert engineer.sap_code == "SAP-USER-001"
        assert engineer.active is True

        await session.rollback()