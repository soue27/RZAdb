from datetime import date

import pytest
from uuid6 import uuid7

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.substations.repository import SubstationRepository
from app.application.tree.service import TreeService
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
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_tree_service_builds_full_enterprise_tree(
    db_session: AsyncSession,
) -> None:
    session = db_session
    holding = Enterprise(
        type=EnterpriseType.HOLDING,
        full_name="Тестовый Холдинг",
        short_name="Тестовый Холдинг",
    )

    branch = Enterprise(
        type=EnterpriseType.BRANCH,
        full_name="Тестовый филиал",
        short_name="Тестовый филиал",
        parent=holding,
    )

    department = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="Тестовое ПО",
        short_name="ТПО",
        parent=branch,
    )

    superadmin = User(
        full_name="Суперадминистратор",
        role=UserRole.SUPERADMIN,
        email=f"tree-superadmin-{uuid7()}@test.local",
        password_hash="test-password-hash",
        enterprise_id=None,
        access_category=AccessCategory.I,
        active=True,
    )

    substation = Substation(
        enterprise=department,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Тестовая",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    connection = Connection(
        substation=substation,
        dispatch_name="ВЛ 110 кВ Тестовая",
        rdu_subordination=False,
    )

    urza = URZA(
        connection=connection,
        dispatch_name="ДЗЛ-110",
        rdu_subordination=False,
        inventory_number="INV-001",
        commissioning_date=date(2026, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.III,
        room_category=RoomCategory.I,
        complexity=False,
    )

    session.add_all([
        holding,
        branch,
        department,
        superadmin,
        substation,
        connection,
        urza,
    ])

    await session.flush()

    access_service = AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )

    tree_service = TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )

    tree = await tree_service.get_tree(
        user_id=superadmin.id,
    )

    assert len(tree) == 1

    holding_node = tree[0]

    assert holding_node.id == holding.id
    assert holding_node.type == EnterpriseType.HOLDING.value
    assert holding_node.full_name == "Тестовый Холдинг"

    assert len(holding_node.children) == 1

    branch_node = holding_node.children[0]

    assert branch_node.id == branch.id
    assert branch_node.type == EnterpriseType.BRANCH.value

    assert len(branch_node.children) == 1

    department_node = branch_node.children[0]

    assert department_node.id == department.id
    assert department_node.type == EnterpriseType.DEPARTMENT.value

    assert len(department_node.substations) == 1

    substation_node = department_node.substations[0]

    assert substation_node.id == substation.id
    assert substation_node.dispatch_name == "ПС Тестовая"

    assert len(substation_node.connections) == 1

    connection_node = substation_node.connections[0]

    assert connection_node.id == connection.id
    assert connection_node.dispatch_name == "ВЛ 110 кВ Тестовая"

    assert len(connection_node.urzas) == 1

    urza_node = connection_node.urzas[0]

    assert urza_node.id == urza.id
    assert urza_node.dispatch_name == "ДЗЛ-110"

@pytest.mark.asyncio
async def test_tree_service_starts_from_specialist_branch(
    db_session: AsyncSession,
) -> None:
    session = db_session
    holding = Enterprise(
        type=EnterpriseType.HOLDING,
        full_name="Холдинг инженера",
        short_name="Холдинг инженера",
    )

    branch = Enterprise(
        type=EnterpriseType.BRANCH,
        full_name="Филиал инженера",
        short_name="Филиал инженера",
        parent=holding,
    )

    department = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="ПО инженера",
        short_name="ПО инженера",
        parent=branch,
    )

    session.add_all([
        holding,
        branch,
        department,
    ])

    await session.flush()

    engineer = User(
        full_name="Инженер",
        role=UserRole.ENGINEER,
        email=f"tree-engineer-{uuid7()}@test.local",
        password_hash="test-password-hash",
        enterprise_id=department.id,
        access_category=AccessCategory.III,
        active=True,
    )

    substation = Substation(
        enterprise=department,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Инженерная",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    connection = Connection(
        substation=substation,
        dispatch_name="ВЛ 110 кВ Инженерная",
        rdu_subordination=False,
    )

    urza = URZA(
        connection=connection,
        dispatch_name="ДЗЛ-Инженерная",
        rdu_subordination=False,
        inventory_number="INV-ENGINEER-001",
        commissioning_date=date(2026, 1, 1),
        status=URZAStatus.IN_OPERATION,
        element_base=ElementBase.MICROPROCESSOR,
        category=URZACategory.III,
        room_category=RoomCategory.I,
        complexity=False,
    )

    session.add_all([
        engineer,
        substation,
        connection,
        urza,
    ])

    await session.flush()

    access_service = AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )

    tree_service = TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )

    tree = await tree_service.get_tree(
        user_id=engineer.id,
    )

    assert len(tree) == 1

    department_node = tree[0]

    assert department_node.id == department.id
    assert department_node.type == EnterpriseType.DEPARTMENT.value
    assert department_node.full_name == "ПО инженера"

    assert len(department_node.children) == 0
    assert len(department_node.substations) == 1

    substation_node = department_node.substations[0]

    assert substation_node.id == substation.id
    assert substation_node.dispatch_name == "ПС Инженерная"

    assert len(substation_node.connections) == 1

    connection_node = substation_node.connections[0]

    assert connection_node.id == connection.id
    assert connection_node.dispatch_name == "ВЛ 110 кВ Инженерная"

    assert len(connection_node.urzas) == 1

    urza_node = connection_node.urzas[0]

    assert urza_node.id == urza.id
    assert urza_node.dispatch_name == "ДЗЛ-Инженерная"

@pytest.mark.asyncio
async def test_tree_service_starts_from_specialist_branch(
    db_session: AsyncSession,
) -> None:
    session = db_session
    holding = Enterprise(
        type=EnterpriseType.HOLDING,
        full_name="Холдинг специалиста",
        short_name="Холдинг специалиста",
    )

    branch_a = Enterprise(
        type=EnterpriseType.BRANCH,
        full_name="Филиал А",
        short_name="Филиал А",
        parent=holding,
    )

    branch_b = Enterprise(
        type=EnterpriseType.BRANCH,
        full_name="Филиал Б",
        short_name="Филиал Б",
        parent=holding,
    )

    department_1 = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="ПО 1",
        short_name="ПО 1",
        parent=branch_a,
    )

    department_2 = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="ПО 2",
        short_name="ПО 2",
        parent=branch_a,
    )

    department_3 = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="ПО 3",
        short_name="ПО 3",
        parent=branch_b,
    )

    session.add_all([
        holding,
        branch_a,
        branch_b,
        department_1,
        department_2,
        department_3,
    ])

    await session.flush()

    specialist = User(
        full_name="Специалист",
        role=UserRole.SPECIALIST,
        email=f"tree-specialist-{uuid7()}@test.local",
        password_hash="test-password-hash",
        enterprise_id=branch_a.id,
        access_category=AccessCategory.III,
        active=True,
    )

    substation_1 = Substation(
        enterprise=department_1,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС 1",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    substation_2 = Substation(
        enterprise=department_2,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС 2",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    substation_3 = Substation(
        enterprise=department_3,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС 3",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    session.add_all([
        specialist,
        substation_1,
        substation_2,
        substation_3,
    ])

    await session.flush()

    access_service = AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )

    tree_service = TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )

    tree = await tree_service.get_tree(
        user_id=specialist.id,
    )

    assert len(tree) == 1

    branch_node = tree[0]

    assert branch_node.id == branch_a.id
    assert branch_node.type == EnterpriseType.BRANCH.value
    assert branch_node.full_name == "Филиал А"

    assert len(branch_node.children) == 2

    department_nodes = {
        node.id: node
        for node in branch_node.children
    }

    assert set(department_nodes) == {
        department_1.id,
        department_2.id,
    }

    assert department_nodes[department_1.id].full_name == "ПО 1"
    assert department_nodes[department_2.id].full_name == "ПО 2"

    assert len(department_nodes[department_1.id].substations) == 1
    assert len(department_nodes[department_2.id].substations) == 1

    assert (
            department_nodes[department_1.id].substations[0].id
            == substation_1.id
    )

    assert (
            department_nodes[department_2.id].substations[0].id
            == substation_2.id
    )

    assert all(
        node.id != branch_b.id
        for node in tree
    )

    assert all(
        node.id != department_3.id
        for node in branch_node.children
    )

@pytest.mark.asyncio
async def test_tree_service_excludes_deleted_enterprises_and_substations(
    db_session: AsyncSession,
) -> None:
    session = db_session
    holding = Enterprise(
            type=EnterpriseType.HOLDING,
            full_name="Холдинг архива",
            short_name="Холдинг архива",
    )

    active_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Активный филиал",
            short_name="Активный филиал",
            parent=holding,
    )

    deleted_branch = Enterprise(
            type=EnterpriseType.BRANCH,
            full_name="Архивный филиал",
            short_name="Архивный филиал",
            parent=holding,
        )

    active_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Активное ПО",
            short_name="Активное ПО",
            parent=active_branch,
    )

    deleted_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Архивное ПО",
            short_name="Архивное ПО",
            parent=active_branch,
    )

    deleted_branch_department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="ПО архивного филиала",
            short_name="ПО архивного филиала",
            parent=deleted_branch,
    )

    session.add_all([
            holding,
            active_branch,
            deleted_branch,
            active_department,
            deleted_department,
            deleted_branch_department,
    ])

    await session.flush()
    deleted_branch.deleted_at = active_branch.created_at
    deleted_department.deleted_at = active_department.created_at
    deleted_branch_department.deleted_at = deleted_branch.created_at

    active_substation = Substation(
        enterprise=active_department,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Активная",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    deleted_substation = Substation(
        enterprise=active_department,
        highest_voltage=HighestVoltage.KV_110,
        dispatch_name="ПС Архивная",
        operational_current_type=OperationalCurrentType.PERMANENT,
    )

    session.add_all([
        active_substation,
        deleted_substation,
    ])

    await session.flush()

    deleted_substation.deleted_at = active_substation.created_at

    superadmin = User(
        full_name="Суперадминистратор архива",
        role=UserRole.SUPERADMIN,
        email=f"tree-archive-superadmin-{uuid7()}@test.local",
        password_hash="test-password-hash",
        enterprise_id=None,
        access_category=AccessCategory.I,
        active=True,
    )

    session.add(superadmin)
    await session.flush()

    access_service = AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )

    tree_service = TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )

    tree = await tree_service.get_tree(
        user_id=superadmin.id,
    )

    assert len(tree) == 1

    holding_node = tree[0]

    assert holding_node.id == holding.id

    assert len(holding_node.children) == 1

    branch_node = holding_node.children[0]

    assert branch_node.id == active_branch.id
    assert branch_node.full_name == "Активный филиал"

    assert len(branch_node.children) == 1

    department_node = branch_node.children[0]

    assert department_node.id == active_department.id
    assert department_node.full_name == "Активное ПО"

    assert len(department_node.substations) == 1

    substation_node = department_node.substations[0]

    assert substation_node.id == active_substation.id
    assert substation_node.dispatch_name == "ПС Активная"

@pytest.mark.asyncio
async def test_tree_service_starts_from_engineer_department(
    db_session: AsyncSession,
):
    session = db_session

    department = Enterprise(
        type=EnterpriseType.DEPARTMENT,
        full_name="ПО Северные сети",
        short_name="ПО Северные сети",
    )
    session.add(department)
    await session.flush()

    user = User(
        email="engineer-tree@example.com",
        password_hash="hash",
        full_name="Инженер дерева",
        role=UserRole.ENGINEER,
        access_category=AccessCategory.IV,
        enterprise_id=department.id,
    )
    session.add(user)
    await session.flush()

    service = TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )

    tree = await service.get_tree(user_id=user.id)

    assert len(tree) == 1
    assert tree[0].type == EnterpriseType.DEPARTMENT.value
    assert tree[0].full_name == "ПО Северные сети"