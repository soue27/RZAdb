from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from uuid6 import uuid7

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    DocumentStatus,
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    TaskStatus,
    TaskWorkType,
    URZACategory,
    URZAStatus,
)
from app.domain.file import File
from app.domain.schema import SchemaForm, SchemaRecord
from app.domain.substation import Substation
from app.domain.task import Task
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_schema_record_status_and_active_unfinished_constraint(
    system_user_id,
) -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Schema constraint department",
            short_name="SCD",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            operational_current_type=OperationalCurrentType.PERMANENT,
            dispatch_name="Schema constraint substation",
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        connection = Connection(
            substation=substation,
            dispatch_name="Schema constraint connection",
            rdu_subordination=True,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        urza = URZA(
            connection=connection,
            dispatch_name="Schema constraint URZA",
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
        task = Task(
            urza=urza,
            work_type=TaskWorkType.SCHEMES,
            status=TaskStatus.IN_PROGRESS,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        schema_form = SchemaForm(
            urza=urza,
            created_by=system_user_id,
            updated_by=system_user_id,
        )
        signed_file = File(
            id=uuid7(),
            s3_key=f"schema-constraint/{uuid7()}.pdf",
            original_name="signed.pdf",
            display_name="Signed schema form",
            extension=".pdf",
            size=1,
            mime_type="application/pdf",
            uploaded_at=datetime.now(UTC),
            created_by=system_user_id,
            updated_by=system_user_id,
        )

        def make_record(
            status: DocumentStatus,
            number: str,
            *,
            task_id=None,
        ) -> SchemaRecord:
            return SchemaRecord(
                schema_form=schema_form,
                schema_number=number,
                schema_name=f"Schema {number}",
                change_description="Schema update",
                change_justification="Test update",
                upload_date=date(2026, 1, 1),
                status=status,
                signed_form_file=signed_file,
                task_id=task_id,
                created_by=system_user_id,
                updated_by=system_user_id,
            )

        draft = make_record(DocumentStatus.DRAFT, "D-1")
        session.add_all([draft, task])
        await session.flush()
        assert draft.status is DocumentStatus.DRAFT

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(make_record(DocumentStatus.UNDER_REVIEW, "R-1"))
                await session.flush()

        draft.deleted_at = datetime.now(UTC)
        draft.deleted_by = system_user_id
        await session.flush()

        under_review = make_record(DocumentStatus.UNDER_REVIEW, "R-2")
        approved_one = make_record(DocumentStatus.APPROVED, "A-1")
        approved_two = make_record(DocumentStatus.APPROVED, "A-2")
        session.add_all([under_review, approved_one, approved_two])
        await session.flush()

        assert under_review.status is DocumentStatus.UNDER_REVIEW
        assert approved_one.status is DocumentStatus.APPROVED
        assert approved_two.status is DocumentStatus.APPROVED

        task_result = make_record(
            DocumentStatus.APPROVED,
            "TASK-1",
            task_id=task.id,
        )
        session.add(task_result)
        await session.flush()

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    make_record(
                        DocumentStatus.APPROVED,
                        "TASK-2",
                        task_id=task.id,
                    )
                )
                await session.flush()

        task_result.deleted_at = datetime.now(UTC)
        task_result.deleted_by = system_user_id
        await session.flush()
        replacement_result = make_record(
            DocumentStatus.APPROVED,
            "TASK-3",
            task_id=task.id,
        )
        session.add(replacement_result)
        await session.flush()

        await session.rollback()
