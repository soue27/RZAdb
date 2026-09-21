from uuid import UUID

from app.application.inspections.inspection_repository import InspectionRepository
from app.application.inspections.schemas import InspectionListItem


class InspectionService:
    """Бизнес-логика работы с результатами осмотров."""

    def __init__(self, repository: InspectionRepository) -> None:
        self.repository = repository

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[InspectionListItem]:
        inspections = await self.repository.get_by_substation_id(
            substation_id,
        )


        return [
            InspectionListItem(
                id=inspection.id,
                substation_id=inspection.substation_id,
                inspection_date=inspection.inspection_date,
                remarks=inspection.remarks,
                created_by=inspection.created_by,
                scan_file_id=(
                    inspection.scan_file.id
                    if inspection.scan_file is not None
                    else None
                ),
                scan_file_name=(
                    inspection.scan_file.display_name
                    if inspection.scan_file is not None
                    else None
                ),
                editable_file_id=(
                    inspection.editable_file.id
                    if inspection.editable_file is not None
                    else None
                ),
                editable_file_name=(
                    inspection.editable_file.display_name
                    if inspection.editable_file is not None
                    else None
                ),
            )
            for inspection in inspections
        ]