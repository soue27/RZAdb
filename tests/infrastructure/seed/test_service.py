from datetime import date

import pytest
from sqlalchemy import func, select

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.seed.service import RZACSVSeedService


def make_row(
    *,
    full_name: str = "Тестовый холдинг",
    short_name: str = "Тестовый холдинг",
) -> dict[str, str]:
    return {
        "holding_full_name": full_name,
        "holding_short_name": short_name,
        "holding_sap_code": "",
    }

@pytest.mark.asyncio
async def test_get_or_create_holding_creates_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            service = RZACSVSeedService(session)

            holding = await service.get_or_create_holding(make_row())

            assert holding.id is not None
            assert holding.type == EnterpriseType.HOLDING
            assert holding.full_name == "Тестовый холдинг"
            assert holding.short_name == "Тестовый холдинг"
            assert holding.sap_code is None
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_holding_returns_existing_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Существующий холдинг",
                short_name="Существующий",
                sap_code="SAP-001",
            )

            session.add(holding)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_holding(
                make_row(
                    full_name="Существующий холдинг",
                    short_name="Другое название",
                )
            )

            assert result.id == holding.id
            assert result.short_name == "Существующий"
            assert result.sap_code == "SAP-001"

            count_result = await session.execute(
                select(func.count())
                .select_from(Enterprise)
                .where(
                    Enterprise.type == EnterpriseType.HOLDING,
                    Enterprise.full_name == "Существующий холдинг",
                    Enterprise.deleted_at.is_(None),
                )
            )

            assert count_result.scalar_one() == 1
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_holding_ignores_deleted_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            deleted_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Архивный холдинг",
                short_name="Архивный",
                deleted_at=func.now(),
            )

            session.add(deleted_holding)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_holding(
                make_row(
                    full_name="Архивный холдинг",
                    short_name="Новый холдинг",
                )
            )

            assert result.id != deleted_holding.id
            assert result.short_name == "Новый холдинг"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_branch_is_scoped_to_holding() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            first_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Первый холдинг",
                short_name="Первый",
            )
            second_holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Второй холдинг",
                short_name="Второй",
            )

            session.add_all([first_holding, second_holding])
            await session.flush()

            first_branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=first_holding.id,
                full_name="Свердловский филиал",
                short_name="Свердловский",
            )

            session.add(first_branch)
            await session.flush()

            service = RZACSVSeedService(session)

            second_branch = await service.get_or_create_branch(
                {
                    "branch_full_name": "Свердловский филиал",
                    "branch_short_name": "Свердловский",
                    "branch_sap_code": "",
                },
                holding_id=second_holding.id,
            )

            assert second_branch.id != first_branch.id
            assert second_branch.parent_id == second_holding.id
            assert second_branch.full_name == "Свердловский филиал"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_branch_returns_existing_branch() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Тестовый холдинг",
                short_name="Тестовый",
            )

            session.add(holding)
            await session.flush()

            branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Существующий филиал",
                short_name="Существующий",
                sap_code="OLD-SAP",
            )

            session.add(branch)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_branch(
                {
                    "branch_full_name": "Существующий филиал",
                    "branch_short_name": "Новое название",
                    "branch_sap_code": "NEW-SAP",
                },
                holding_id=holding.id,
            )

            assert result.id == branch.id
            assert result.short_name == "Существующий"
            assert result.sap_code == "OLD-SAP"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_department_creates_department() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Тестовый холдинг",
                short_name="Тестовый",
            )
            session.add(holding)
            await session.flush()

            branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Тестовый филиал",
                short_name="Тестовый филиал",
            )
            session.add(branch)
            await session.flush()

            service = RZACSVSeedService(session)

            department = await service.get_or_create_department(
                {
                    "department_full_name": "ПО Центральные сети",
                    "department_short_name": "Центральные сети",
                    "department_sap_code": "PO-001",
                },
                branch_id=branch.id,
            )

            assert department.id is not None
            assert department.type == EnterpriseType.DEPARTMENT
            assert department.parent_id == branch.id
            assert department.full_name == "ПО Центральные сети"
            assert department.short_name == "Центральные сети"
            assert department.sap_code == "PO-001"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_department_is_scoped_to_branch() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Тестовый холдинг",
                short_name="Тестовый",
            )
            session.add(holding)
            await session.flush()

            first_branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Первый филиал",
                short_name="Первый",
            )
            second_branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Второй филиал",
                short_name="Второй",
            )
            session.add_all([first_branch, second_branch])
            await session.flush()

            first_department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                parent_id=first_branch.id,
                full_name="ПО Центральные сети",
                short_name="Центральные сети",
            )
            session.add(first_department)
            await session.flush()

            service = RZACSVSeedService(session)

            second_department = await service.get_or_create_department(
                {
                    "department_full_name": "ПО Центральные сети",
                    "department_short_name": "Центральные сети",
                    "department_sap_code": "",
                },
                branch_id=second_branch.id,
            )

            assert second_department.id != first_department.id
            assert second_department.parent_id == second_branch.id
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_department_returns_existing_department() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            holding = Enterprise(
                type=EnterpriseType.HOLDING,
                full_name="Тестовый холдинг",
                short_name="Тестовый",
            )
            session.add(holding)
            await session.flush()

            branch = Enterprise(
                type=EnterpriseType.BRANCH,
                parent_id=holding.id,
                full_name="Тестовый филиал",
                short_name="Тестовый",
            )
            session.add(branch)
            await session.flush()

            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                parent_id=branch.id,
                full_name="ПО Центральные сети",
                short_name="Существующее",
                sap_code="OLD-SAP",
            )
            session.add(department)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_department(
                {
                    "department_full_name": "ПО Центральные сети",
                    "department_short_name": "Новое название",
                    "department_sap_code": "NEW-SAP",
                },
                branch_id=branch.id,
            )

            assert result.id == department.id
            assert result.short_name == "Существующее"
            assert result.sap_code == "OLD-SAP"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_substation_creates_substation() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные сети",
            )

            session.add(department)
            await session.flush()

            service = RZACSVSeedService(session)

            substation = await service.get_or_create_substation(
                {
                    "substation_dispatch_name": "ПС Свердловская",
                    "substation_highest_voltage": "110",
                    "substation_sap_code": "PS-001",
                    "substation_asureo_code": "ASUREO-001",
                    "substation_address": "г. Екатеринбург",
                    "substation_latitude": "56.123456",
                    "substation_longitude": "60.123456",
                },
                department_id=department.id,
            )

            assert substation.id is not None
            assert substation.enterprise_id == department.id
            assert substation.dispatch_name == "ПС Свердловская"
            assert substation.highest_voltage.value == "110"
            assert substation.sap_code == "PS-001"
            assert substation.asureo_code == "ASUREO-001"
            assert str(substation.latitude) == "56.123456"
            assert str(substation.longitude) == "60.123456"
            assert substation.address == "г. Екатеринбург"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_substation_returns_existing_substation() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )

            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
                sap_code="OLD-SAP",
            )

            session.add(substation)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_substation(
                {
                    "substation_dispatch_name": "ПС Свердловская",
                    "substation_highest_voltage": "220",
                    "substation_sap_code": "NEW-SAP",
                },
                department_id=department.id,
            )

            assert result.id == substation.id
            assert result.highest_voltage == HighestVoltage.KV_110
            assert result.sap_code == "OLD-SAP"
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_substation_ignores_deleted_substation() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )

            session.add(department)
            await session.flush()

            deleted_substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
                deleted_at=func.now(),
            )

            session.add(deleted_substation)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_substation(
                {
                    "substation_dispatch_name": "ПС Свердловская",
                    "substation_highest_voltage": "110",
                },
                department_id=department.id,
            )

            assert result.id != deleted_substation.id
            assert result.deleted_at is None
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_connection_creates_connection() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            service = RZACSVSeedService(session)

            connection = await service.get_or_create_connection(
                {
                    "connection_dispatch_name": "ВЛ 110 кВ Свердловская",
                    "connection_sap_code": "CON-001",
                    "connection_asureo_code": "ASUREO-CON-001",
                    "connection_rdu_subordination": "да",
                    "operational_current_type": "permanent",
                },
                substation_id=substation.id,
            )

            assert connection.id is not None
            assert connection.substation_id == substation.id
            assert connection.dispatch_name == "ВЛ 110 кВ Свердловская"
            assert connection.sap_code == "CON-001"
            assert connection.asureo_code == "ASUREO-CON-001"
            assert connection.rdu_subordination is True
            assert (
                connection.operational_current_type
                == OperationalCurrentType.PERMANENT
            )
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_connection_parses_values() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            service = RZACSVSeedService(session)

            connection = await service.get_or_create_connection(
                {
                    "connection_dispatch_name": "Трансформатор Т-1",
                    "connection_sap_code": "",
                    "connection_asureo_code": "",
                    "connection_rdu_subordination": "нет",
                    "operational_current_type": "rectified",
                },
                substation_id=substation.id,
            )

            assert connection.rdu_subordination is False
            assert (
                connection.operational_current_type
                == OperationalCurrentType.RECTIFIED
            )
            assert connection.sap_code is None
            assert connection.asureo_code is None
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_connection_returns_existing_connection() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            connection = Connection(
                substation_id=substation.id,
                dispatch_name="ВЛ 110 кВ Свердловская",
                sap_code="OLD-SAP",
                rdu_subordination=True,
                operational_current_type=OperationalCurrentType.PERMANENT,
            )
            session.add(connection)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_connection(
                {
                    "connection_dispatch_name": "ВЛ 110 кВ Свердловская",
                    "connection_sap_code": "NEW-SAP",
                    "connection_asureo_code": "NEW-ASUREO",
                    "connection_rdu_subordination": "нет",
                    "operational_current_type": "rectified",
                },
                substation_id=substation.id,
            )

            assert result.id == connection.id
            assert result.sap_code == "OLD-SAP"
            assert result.rdu_subordination is True
            assert (
                result.operational_current_type
                == OperationalCurrentType.PERMANENT
            )
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_urza_creates_urza() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            connection = Connection(
                substation_id=substation.id,
                dispatch_name="ВЛ 110 кВ Свердловская",
                rdu_subordination=True,
                operational_current_type=OperationalCurrentType.PERMANENT,
            )
            session.add(connection)
            await session.flush()

            service = RZACSVSeedService(session)

            urza = await service.get_or_create_urza(
                {
                    "urza_dispatch_name": "ДЗЛ-110",
                    "urza_rdu_subordination": "да",
                    "urza_inventory_number": "INV-001",
                    "urza_commissioning_date": "2024-05-15",
                    "urza_status": "in_operation",
                    "urza_element_base": "microprocessor",
                    "urza_category": "II",
                    "urza_room_category": "I",
                    "urza_complexity": "нет",
                },
                connection_id=connection.id,
            )

            assert urza.id is not None
            assert urza.connection_id == connection.id
            assert urza.dispatch_name == "ДЗЛ-110"
            assert urza.rdu_subordination is True
            assert urza.inventory_number == "INV-001"
            assert urza.commissioning_date == date(2024, 5, 15)
            assert urza.status == URZAStatus.IN_OPERATION
            assert urza.element_base == ElementBase.MICROPROCESSOR
            assert urza.category == URZACategory.II
            assert urza.room_category == RoomCategory.I
            assert urza.complexity is False
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_urza_allows_empty_inventory_number() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            connection = Connection(
                substation_id=substation.id,
                dispatch_name="ВЛ 110 кВ Свердловская",
                rdu_subordination=False,
                operational_current_type=OperationalCurrentType.RECTIFIED,
            )
            session.add(connection)
            await session.flush()

            service = RZACSVSeedService(session)

            urza = await service.get_or_create_urza(
                {
                    "urza_dispatch_name": "УРОВ",
                    "urza_rdu_subordination": "нет",
                    "urza_inventory_number": "",
                    "urza_commissioning_date": "2025-01-10",
                    "urza_status": "reserve",
                    "urza_element_base": "microelectronic",
                    "urza_category": "III",
                    "urza_room_category": "II",
                    "urza_complexity": "да",
                },
                connection_id=connection.id,
            )

            assert urza.inventory_number is None
            assert urza.status == URZAStatus.RESERVE
            assert urza.element_base == ElementBase.MICROELECTRONIC
            assert urza.category == URZACategory.III
            assert urza.room_category == RoomCategory.II
            assert urza.complexity is True
        finally:
            await transaction.rollback()

@pytest.mark.asyncio
async def test_get_or_create_urza_returns_existing_urza() -> None:
    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            department = Enterprise(
                type=EnterpriseType.DEPARTMENT,
                full_name="ПО Центральные сети",
                short_name="Центральные",
            )
            session.add(department)
            await session.flush()

            substation = Substation(
                enterprise_id=department.id,
                highest_voltage=HighestVoltage.KV_110,
                dispatch_name="ПС Свердловская",
            )
            session.add(substation)
            await session.flush()

            connection = Connection(
                substation_id=substation.id,
                dispatch_name="ВЛ 110 кВ Свердловская",
                rdu_subordination=True,
                operational_current_type=OperationalCurrentType.PERMANENT,
            )
            session.add(connection)
            await session.flush()

            urza = URZA(
                connection_id=connection.id,
                dispatch_name="ДЗЛ-110",
                rdu_subordination=True,
                inventory_number="OLD-001",
                commissioning_date=date(2024, 5, 15),
                status=URZAStatus.IN_OPERATION,
                element_base=ElementBase.MICROPROCESSOR,
                category=URZACategory.II,
                room_category=RoomCategory.I,
                complexity=False,
            )
            session.add(urza)
            await session.flush()

            service = RZACSVSeedService(session)

            result = await service.get_or_create_urza(
                {
                    "urza_dispatch_name": "ДЗЛ-110",
                    "urza_rdu_subordination": "нет",
                    "urza_inventory_number": "NEW-001",
                    "urza_commissioning_date": "2026-01-01",
                    "urza_status": "in_repair",
                    "urza_element_base": "electromechanical",
                    "urza_category": "IV",
                    "urza_room_category": "III",
                    "urza_complexity": "да",
                },
                connection_id=connection.id,
            )

            assert result.id == urza.id
            assert result.inventory_number == "OLD-001"
            assert result.status == URZAStatus.IN_OPERATION
            assert result.element_base == ElementBase.MICROPROCESSOR
            assert result.category == URZACategory.II
            assert result.room_category == RoomCategory.I
            assert result.complexity is False
        finally:
            await transaction.rollback()

