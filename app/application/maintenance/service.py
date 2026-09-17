from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.maintenance.repository import TORecordRepository
from app.domain.enums import MaintenanceType
from app.domain.maintenance import TORecord


class TORecordService:
    def __init__(
        self,
        repository: TORecordRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[TORecord]:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_urza_id(
            urza_id,
        )

    async def get_by_task(
        self,
        user_id: UUID,
        task_id: UUID,
        urza_id: UUID,
    ) -> TORecord | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_task_id(
            task_id,
        )

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        maintenance_date: date,
        maintenance_type: MaintenanceType,
        signed_form_file_id: UUID,
        scan_protocol_id: UUID | None = None,
        editable_protocol_id: UUID | None = None,
        detected_deviations: str = "Не выявлено",
        measures_taken: str = "Не требуется",
        historical_data: str | None = None,
        task_id: UUID | None = None,
    ) -> TORecord:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        if maintenance_type not in {
            MaintenanceType.TK,
            MaintenanceType.O,
            MaintenanceType.OSM,
        } and scan_protocol_id is None:
            raise ValueError(
                "Для данного типа ТО требуется протокол"
            )

        record = TORecord(
            urza_id=urza_id,
            historical_data=historical_data,
            maintenance_date=maintenance_date,
            maintenance_type=maintenance_type,
            detected_deviations=detected_deviations,
            measures_taken=measures_taken,
            created_by=user_id,
            scan_protocol_id=scan_protocol_id,
            editable_protocol_id=editable_protocol_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )

        await self.repository.add(record)

        return record

    async def get_by_id(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
    ) -> TORecord | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_id(
            record_id,
        )