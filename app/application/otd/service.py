from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.otd.repository import OTDRepository
from app.domain.enums import OTDPurpose
from app.domain.otd import OTD, OTDVersion
from app.application.otd.schemas import OTDDetails, OTDVersionDetails


class OTDService:
    def __init__(
        self,
        repository: OTDRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    def _to_version_details(self, version: OTDVersion) -> OTDVersionDetails:
        return OTDVersionDetails(
            id=version.id,
            version_number=version.version_number,
            effective_date=version.effective_date,
            panel_cabinet_type=version.panel_cabinet_type,
            panel_cabinet_serial=version.panel_cabinet_serial,
            panel_cabinet_manufacture_year=version.panel_cabinet_manufacture_year,
            terminal_type=version.terminal_type,
            terminal_serial=version.terminal_serial,
            terminal_manufacture_year=version.terminal_manufacture_year,
            urza_service_life=version.urza_service_life,
            software_version=version.software_version,
            ct_ratio=version.ct_ratio,
            vt_ratio=version.vt_ratio,
            urza_scheme_designation=version.urza_scheme_designation,
            urza_purpose=version.urza_purpose,
            created_at=version.created_at,
        )

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> OTD | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            return None

        return await self.repository.get_by_urza_id(urza_id)

    async def get_current_version(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> OTDVersion | None:
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            return None

        otd = await self.repository.get_by_urza_id(urza_id)

        if otd is None:
            return None

        return await self.repository.get_current_version(otd.id)

    async def get_versions(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> list[OTDVersion]:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return []

        otd = await self.repository.get_by_urza_id(urza_id)
        if otd is None:
            return []

        return await self.repository.get_versions(otd.id)

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        effective_date: date,
        urza_service_life: int,
        urza_purpose: OTDPurpose,
    ) -> OTD:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        existing_otd = await self.repository.get_by_urza_id(urza_id)

        if existing_otd is not None:
            raise ValueError("OTD для данного URZA уже существует")

        otd = OTD(
            urza_id=urza_id,
        )

        await self.repository.add(otd)

        version = OTDVersion(
            otd_id=otd.id,
            version_number=1,
            effective_date=effective_date,
            urza_service_life=urza_service_life,
            urza_purpose=urza_purpose,
        )

        await self.repository.add_version(version)

        return otd

    async def create_version(
            self,
            user_id: UUID,
            otd_id: UUID,
            effective_date: date,
            urza_service_life: int,
            urza_purpose: OTDPurpose,
            **kwargs,
    ) -> OTDVersion:
        otd = await self.repository.get_by_id(otd_id)

        if otd is None:
            raise ValueError("OTD не найден")

        if not await self.access_service.can_access_urza(
                user_id,
                otd.urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        current_version = await self.repository.get_current_version(otd_id)

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = OTDVersion(
            otd_id=otd_id,
            version_number=version_number,
            effective_date=effective_date,
            urza_service_life=urza_service_life,
            urza_purpose=urza_purpose,
            **kwargs,
        )

        await self.repository.add_version(version)

        return version

    async def get_details(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> OTDDetails | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return None

        otd = await self.repository.get_by_urza_id(urza_id)
        if otd is None:
            return None

        versions = await self.repository.get_versions(otd.id)

        version_details = [
            self._to_version_details(version)
            for version in versions
        ]

        return OTDDetails(
            id=otd.id,
            current_version=version_details[0] if version_details else None,
            versions=version_details,
        )