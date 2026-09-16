from uuid6 import uuid7

import pytest

from app.application.access.service import AccessService
from app.application.substations.repository import SubstationRepository
from app.application.users.repository import UserRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    EnterpriseType,
    HighestVoltage,
    UserRole,
)
from app.domain.substation import Substation
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory
from app.application.enterprises.repository import EnterpriseRepository


@pytest.mark.asyncio
async def test_superadmin_can_access_any_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое ПО",
            short_name="ТПО",
        )

        superadmin = User(
            full_name="Суперадминистратор",
            role=UserRole.SUPERADMIN,
            email=f"superadmin-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.I,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
        )

        session.add_all([department, superadmin, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=superadmin.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_can_access_substation_of_own_department() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Своего ПО",
        )

        session.add_all([department, engineer, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=engineer.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_engineer_cannot_access_substation_of_another_department() -> None:
    async with async_session_factory() as session:
        own_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        another_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Другое ПО",
            short_name="ДРУГОЕ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=own_department,
            access_category=AccessCategory.III,
            active=True,
        )

        substation = Substation(
            enterprise=another_department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Другого ПО",
        )

        session.add_all([
            own_department,
            another_department,
            engineer,
            substation,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=engineer.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_admin_can_access_substation_of_own_department() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Администратора",
            short_name="ПО АДМ",
        )

        admin = User(
            full_name="Администратор",
            role=UserRole.ADMIN,
            email=f"admin-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_220,
            dispatch_name="ПС Администратора",
        )

        session.add_all([department, admin, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=admin.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_manager_can_access_substation_of_own_department() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Руководителя",
            short_name="ПО РУК",
        )

        manager = User(
            full_name="Руководитель",
            role=UserRole.MANAGER,
            email=f"manager-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Руководителя",
        )

        session.add_all([department, manager, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=manager.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_unknown_user_cannot_access_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
        )

        session.add_all([department, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=uuid7(),
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_inactive_user_cannot_access_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        user = User(
            full_name="Неактивный инженер",
            role=UserRole.ENGINEER,
            email=f"inactive-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            active=False,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
        )

        session.add_all([department, user, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=user.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_user_cannot_access_unknown_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        user = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            active=True,
        )

        session.add_all([department, user])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=user.id,
            substation_id=uuid7(),
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_deleted_user_cannot_access_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        user = User(
            full_name="Удалённый инженер",
            role=UserRole.ENGINEER,
            email=f"deleted-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
        )

        session.add_all([department, user, substation])
        await session.flush()

        user.deleted_at = user.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=user.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()


@pytest.mark.asyncio
async def test_deleted_substation_cannot_be_accessed() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        user = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.III,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="Удалённая ПС",
        )

        session.add_all([department, user, substation])
        await session.flush()

        substation.deleted_at = substation.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=user.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()


@pytest.mark.asyncio
async def test_user_without_enterprise_cannot_access_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО Тестовое",
            short_name="ПО ТЕСТ",
        )

        user = User(
            full_name="Инженер без ПО",
            role=UserRole.ENGINEER,
            email=f"no-enterprise-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.III,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
        )

        session.add_all([department, user, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=user.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_can_access_substation_inside_holding() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Филиал",
            short_name="Ф",
            parent=holding,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО",
            short_name="ПО",
            parent=branch,
        )

        specialist = User(
            full_name="Специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=holding,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Холдинга",
        )

        session.add_all([holding, branch, department, specialist, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=specialist.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_specialist_can_access_substation_inside_own_branch() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
        )

        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Свой филиал",
            short_name="СФ",
            parent=holding,
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СПО",
            parent=branch,
        )

        specialist = User(
            full_name="Специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=branch,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Своего филиала",
        )

        session.add_all([holding, branch, department, specialist, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=specialist.id,
            substation_id=substation.id,
        )

        assert result is True

        await session.rollback()


@pytest.mark.asyncio
async def test_specialist_cannot_access_substation_of_another_branch() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="Х",
        )

        own_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Свой филиал",
            short_name="СФ",
            parent=holding,
        )

        another_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Другой филиал",
            short_name="ДФ",
            parent=holding,
        )

        own_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СПО",
            parent=own_branch,
        )

        another_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Другое ПО",
            short_name="ДПО",
            parent=another_branch,
        )

        specialist = User(
            full_name="Специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=own_branch,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=another_department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Другого филиала",
        )

        session.add_all([
            holding,
            own_branch,
            another_branch,
            own_department,
            another_department,
            specialist,
            substation,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=specialist.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_with_department_scope_cannot_access_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО",
            short_name="ПО",
        )

        specialist = User(
            full_name="Некорректный специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=department,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС ПО",
        )

        session.add_all([department, specialist, substation])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_substation(
            user_id=specialist.id,
            substation_id=substation.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_superadmin_can_access_any_enterprise() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )
        superadmin = User(
            full_name="Superadmin",
            role=UserRole.SUPERADMIN,
            email="superadmin-enterprise@test.local",
            password_hash="hash",
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([enterprise, superadmin])
        await session.flush()

        repository = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await repository.can_access_enterprise(
            user_id=superadmin.id,
            enterprise_id=enterprise.id,
        )

        assert result is True
        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_can_access_own_enterprise() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )
        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-enterprise@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add(engineer)
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=engineer.id,
            enterprise_id=enterprise.id,
        )

        assert result is True
        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_cannot_access_another_enterprise() -> None:
    async with async_session_factory() as session:
        own_enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Own Department",
            short_name="Own Department",
        )
        another_enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Another Department",
            short_name="Another Department",
        )
        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-another-enterprise@test.local",
            password_hash="hash",
            enterprise=own_enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([another_enterprise, engineer])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=engineer.id,
            enterprise_id=another_enterprise.id,
        )

        assert result is False
        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_can_access_descendant_enterprise() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Holding",
            short_name="Holding",
        )
        branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch",
            short_name="Branch",
            parent=holding,
        )
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
            parent=branch,
        )
        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-descendant@test.local",
            password_hash="hash",
            access_category=AccessCategory.IV,
            enterprise=holding,
            active=True,
        )

        session.add_all([department, specialist])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department.id,
        )

        assert result is True
        await session.rollback()