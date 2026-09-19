from datetime import UTC, date, datetime

import pytest
from uuid6 import uuid7

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    AccessCategory,
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
    UserRole,
)
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory


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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),

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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
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
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department.id,
        )

        assert result is True
        await session.rollback()

@pytest.mark.asyncio
async def test_can_access_enterprise_returns_false_for_deleted_user() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )
        user = User(
            full_name="Deleted User",
            role=UserRole.ENGINEER,
            email="deleted-enterprise@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add(user)
        await session.flush()

        user.deleted_at = user.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=user.id,
            enterprise_id=enterprise.id,
        )

        assert result is False
        await session.rollback()

@pytest.mark.asyncio
async def test_can_access_enterprise_returns_false_for_inactive_user() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )
        user = User(
            full_name="Inactive User",
            role=UserRole.ENGINEER,
            email="inactive-enterprise@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=False,
        )

        session.add(user)
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=user.id,
            enterprise_id=enterprise.id,
        )

        assert result is False
        await session.rollback()

@pytest.mark.asyncio
async def test_can_access_enterprise_returns_false_for_deleted_enterprise() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Deleted Department",
            short_name="Deleted Department",
        )
        user = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="deleted-enterprise-target@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add(user)
        await session.flush()

        enterprise.deleted_at = enterprise.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=user.id,
            enterprise_id=enterprise.id,
        )

        assert result is False
        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_cannot_access_with_deleted_own_enterprise() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Deleted Holding",
            short_name="Deleted Holding",
        )
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
            parent=holding,
        )
        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-deleted-holding@test.local",
            password_hash="hash",
            enterprise=holding,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([department, specialist])
        await session.flush()

        holding.deleted_at = holding.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department.id,
        )

        assert result is False
        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_can_access_departments_in_different_branches() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Holding",
            short_name="Holding",
        )

        branch_a = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch A",
            short_name="Branch A",
            parent=holding,
        )
        branch_b = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch B",
            short_name="Branch B",
            parent=holding,
        )

        department_a = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department A",
            short_name="Department A",
            parent=branch_a,
        )
        department_b = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department B",
            short_name="Department B",
            parent=branch_b,
        )

        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-two-branches@test.local",
            password_hash="hash",
            enterprise=holding,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([
            department_a,
            department_b,
            specialist,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result_a = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department_a.id,
        )
        result_b = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department_b.id,
        )

        assert result_a is True
        assert result_b is True

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_cannot_access_department_in_another_branch() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Holding",
            short_name="Holding",
        )

        branch_a = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch A",
            short_name="Branch A",
            parent=holding,
        )
        branch_b = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch B",
            short_name="Branch B",
            parent=holding,
        )

        department_a = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department A",
            short_name="Department A",
            parent=branch_a,
        )
        department_b = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department B",
            short_name="Department B",
            parent=branch_b,
        )

        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-branch-boundary@test.local",
            password_hash="hash",
            enterprise=branch_a,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([
            department_a,
            department_b,
            specialist,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        own_department = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department_a.id,
        )
        foreign_department = await service.can_access_enterprise(
            user_id=specialist.id,
            enterprise_id=department_b.id,
        )

        assert own_department is True
        assert foreign_department is False

        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_can_access_connection_in_own_department() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )

        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-110",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-connection@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([connection, engineer])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_connection(
            user_id=engineer.id,
            connection_id=connection.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_cannot_access_connection_in_another_department() -> None:
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

        own_substation = Substation(
            enterprise=own_enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="Own PS",
        )
        another_substation = Substation(
            enterprise=another_enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="Another PS",
        )

        own_connection = Connection(
            substation=own_substation,
            dispatch_name="Own Connection",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )
        another_connection = Connection(
            substation=another_substation,
            dispatch_name="Another Connection",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-foreign-connection@test.local",
            password_hash="hash",
            enterprise=own_enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([
            own_connection,
            another_connection,
            engineer,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        own_result = await service.can_access_connection(
            user_id=engineer.id,
            connection_id=own_connection.id,
        )
        foreign_result = await service.can_access_connection(
            user_id=engineer.id,
            connection_id=another_connection.id,
        )

        assert own_result is True
        assert foreign_result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_can_access_connection_in_own_branch() -> None:
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

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-110",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-connection@test.local",
            password_hash="hash",
            enterprise=branch,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([connection, specialist])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_connection(
            user_id=specialist.id,
            connection_id=connection.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_cannot_access_connection_in_another_branch() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Holding",
            short_name="Holding",
        )

        branch_a = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch A",
            short_name="Branch A",
            parent=holding,
        )
        branch_b = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Branch B",
            short_name="Branch B",
            parent=holding,
        )

        department_a = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department A",
            short_name="Department A",
            parent=branch_a,
        )
        department_b = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department B",
            short_name="Department B",
            parent=branch_b,
        )

        substation_a = Substation(
            enterprise=department_a,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-A",
        )
        substation_b = Substation(
            enterprise=department_b,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-B",
        )

        connection_a = Connection(
            substation=substation_a,
            dispatch_name="Connection A",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )
        connection_b = Connection(
            substation=substation_b,
            dispatch_name="Connection B",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        specialist = User(
            full_name="Specialist",
            role=UserRole.SPECIALIST,
            email="specialist-foreign-connection@test.local",
            password_hash="hash",
            enterprise=branch_a,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([
            connection_a,
            connection_b,
            specialist,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        own_result = await service.can_access_connection(
            user_id=specialist.id,
            connection_id=connection_a.id,
        )
        foreign_result = await service.can_access_connection(
            user_id=specialist.id,
            connection_id=connection_b.id,
        )

        assert own_result is True
        assert foreign_result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_can_access_connection_returns_false_for_deleted_connection() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )

        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="PS-110",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-deleted-connection@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([connection, engineer])
        await session.flush()

        connection.deleted_at = connection.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_connection(
            user_id=engineer.id,
            connection_id=connection.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_can_access_connection_returns_false_for_deleted_substation() -> None:
    async with async_session_factory() as session:
        enterprise = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Department",
            short_name="Department",
        )

        substation = Substation(
            enterprise=enterprise,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="Deleted PS",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Connection 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        engineer = User(
            full_name="Engineer",
            role=UserRole.ENGINEER,
            email="engineer-deleted-substation@test.local",
            password_hash="hash",
            enterprise=enterprise,
            access_category=AccessCategory.IV,
            active=True,
        )

        session.add_all([connection, engineer])
        await session.flush()

        substation.deleted_at = substation.created_at

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_connection(
            user_id=engineer.id,
            connection_id=connection.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_can_access_urza_of_own_department() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-urza-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        session.add_all([
            department,
            engineer,
            substation,
            connection,
            urza,
        ])
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=engineer.id,
            urza_id=urza.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_engineer_cannot_access_urza_of_another_department() -> None:
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
            email=f"engineer-urza-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        session.add_all(
            [
                own_department,
                another_department,
                engineer,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=engineer.id,
            urza_id=urza.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_cannot_access_deleted_urza() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-deleted-urza-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="Удалённое РЗА",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        urza.deleted_at = datetime.now(UTC)

        session.add_all(
            [
                department,
                engineer,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=engineer.id,
            urza_id=urza.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_cannot_access_urza_of_deleted_connection() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-deleted-connection-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Удалённое присоединение",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        connection.deleted_at = datetime.now(UTC)

        session.add_all(
            [
                department,
                engineer,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=engineer.id,
            urza_id=urza.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_cannot_access_urza_of_deleted_substation() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Своё ПО",
            short_name="СВОЁ ПО",
        )

        engineer = User(
            full_name="Инженер",
            role=UserRole.ENGINEER,
            email=f"engineer-deleted-substation-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        substation.deleted_at = datetime.now(UTC)

        session.add_all(
            [
                department,
                engineer,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=engineer.id,
            urza_id=urza.id,
        )

        assert result is False

        await session.rollback()

@pytest.mark.asyncio
async def test_superadmin_can_access_urza_of_any_department() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Другое ПО",
            short_name="ДРУГОЕ ПО",
        )

        superadmin = User(
            full_name="Суперадминистратор",
            role=UserRole.SUPERADMIN,
            email=f"superadmin-urza-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise_id=None,
            access_category=AccessCategory.I,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Другого ПО",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        session.add_all(
            [
                department,
                superadmin,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=superadmin.id,
            urza_id=urza.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_can_access_urza_in_holding_descendant() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="ХОЛДИНГ",
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            parent=holding,
            full_name="ПО Холдинга",
            short_name="ПО ХОЛДИНГА",
        )

        specialist = User(
            full_name="Специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-urza-{uuid7()}@test.local",
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

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        session.add_all(
            [
                holding,
                department,
                specialist,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=specialist.id,
            urza_id=urza.id,
        )

        assert result is True

        await session.rollback()

@pytest.mark.asyncio
async def test_specialist_cannot_access_urza_in_another_branch() -> None:
    async with async_session_factory() as session:
        holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг",
            short_name="ХОЛДИНГ",
        )

        own_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            parent=holding,
            full_name="Свой филиал",
            short_name="СВОЙ ФИЛИАЛ",
        )

        another_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            parent=holding,
            full_name="Другой филиал",
            short_name="ДРУГОЙ ФИЛИАЛ",
        )

        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            parent=another_branch,
            full_name="ПО другого филиала",
            short_name="ПО ДРУГОГО ФИЛИАЛА",
        )

        specialist = User(
            full_name="Специалист",
            role=UserRole.SPECIALIST,
            email=f"specialist-other-branch-urza-{uuid7()}@test.local",
            password_hash="test-password-hash",
            enterprise=own_branch,
            access_category=AccessCategory.IV,
            active=True,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Другого филиала",
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Присоединение 1",
            rdu_subordination=False,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="РЗА-1",
            rdu_subordination=False,
            inventory_number=None,
            commissioning_date=date(2020, 1, 1),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=False,
        )

        session.add_all(
            [
                holding,
                own_branch,
                another_branch,
                department,
                specialist,
                substation,
                connection,
                urza,
            ]
        )
        await session.flush()

        service = AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        )

        result = await service.can_access_urza(
            user_id=specialist.id,
            urza_id=urza.id,
        )

        assert result is False

        await session.rollback()