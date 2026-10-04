from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    DocumentStatus,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.domain.rza_settings import SettingsForm
from app.domain.file import File
from app.domain.settings_record import SettingsRecord
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_urza_can_have_only_one_settings_form(system_user_id) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
            operational_current_type=OperationalCurrentType.PERMANENT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Ввод 110 кВ",
            rdu_subordination=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="ДЗЛ 110 кВ",
            rdu_subordination=False,
            commissioning_date=date(2020, 5, 15),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        first_form = SettingsForm(
            urza=urza, created_by=system_user_id, updated_by=system_user_id
        )
        second_form = SettingsForm(
            urza=urza, created_by=system_user_id, updated_by=system_user_id
        )

        session.add(first_form)
        await session.flush()

        session.add(second_form)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()


@pytest.mark.asyncio
async def test_settings_form_allows_only_one_active_unfinished_record(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Settings constraint department",
            short_name="SCD",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            operational_current_type=OperationalCurrentType.PERMANENT,
            dispatch_name="Settings constraint substation",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        connection = Connection(
            substation=substation,
            dispatch_name="Settings constraint connection",
            rdu_subordination=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        urza = URZA(
            connection=connection,
            dispatch_name="Settings constraint URZA",
            rdu_subordination=False,
            commissioning_date=date(2020, 5, 15),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        settings_form = SettingsForm(
            urza=urza,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        signed_file = File(
            s3_key=f"settings-constraint-{urza.id}",
            original_name="signed.pdf",
            display_name="Signed settings form",
            extension=".pdf",
            size=1,
            mime_type="application/pdf",
            uploaded_at=datetime.now(UTC),
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        first = SettingsRecord(
            settings_form=settings_form,
            change_date=date(2026, 1, 1),
            parameter_name="P1",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file=signed_file,
            status=DocumentStatus.DRAFT,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add(first)
        await session.flush()

        conflicting = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=date(2026, 1, 2),
            parameter_name="P2",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file_id=signed_file.id,
            status=DocumentStatus.UNDER_REVIEW,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(conflicting)
                await session.flush()

        first.deleted_at = datetime.now(UTC)
        first.deleted_by = system_user_id
        await session.flush()

        replacement = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=date(2026, 1, 3),
            parameter_name="P3",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file_id=signed_file.id,
            status=DocumentStatus.UNDER_REVIEW,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        approved = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=date(2026, 1, 4),
            parameter_name="P4",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file_id=signed_file.id,
            status=DocumentStatus.APPROVED,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        second_approved = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=date(2026, 1, 5),
            parameter_name="P5",
            initial_setting="1",
            new_setting="2",
            change_reason="Test",
            signed_form_file_id=signed_file.id,
            status=DocumentStatus.APPROVED,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        session.add_all([replacement, approved, second_approved])
        await session.flush()
        await session.rollback()
