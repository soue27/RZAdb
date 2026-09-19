from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.schema.repository import SchemaRepository
from app.domain.schema import SchemaForm, SchemaRecord


class SchemaService:
    def __init__(
        self,
        repository: SchemaRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaForm | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            return None

        return await self.repository.get_form_by_urza_id(
            urza_id,
        )

    async def create_form(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> SchemaForm:
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        existing_form = await self.repository.get_form_by_urza_id(
            urza_id,
        )

        if existing_form is not None:
            raise ValueError(
                "Форма схем для данного URZA уже существует"
            )

        schema_form = SchemaForm(
            urza_id=urza_id,
        )

        await self.repository.add_form(schema_form)

        return schema_form

    async def create_record(
            self,
            user_id: UUID,
            urza_id: UUID,
            schema_number: str,
            schema_name: str,
            change_description: str,
            change_justification: str,
            upload_date: date,
            signed_form_file_id: UUID,
            scan_file_id: UUID | None = None,
            editable_file_id: UUID | None = None,
            task_id: UUID | None = None,
    ) -> SchemaRecord:
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        schema_form = await self.repository.get_form_by_urza_id(
            urza_id,
        )

        if schema_form is None:
            raise ValueError(
                "Форма схем для данного URZA не существует"
            )

        record = SchemaRecord(
            schema_form_id=schema_form.id,
            schema_number=schema_number,
            schema_name=schema_name,
            change_description=change_description,
            change_justification=change_justification,
            upload_date=upload_date,
            created_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )

        await self.repository.add_record(record)

        return record