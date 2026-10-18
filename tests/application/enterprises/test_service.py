import pytest
from uuid6 import uuid7

from app.application.enterprises.schemas import EnterpriseUpdate
from app.application.enterprises.service import EnterpriseService
from app.application.objects.exceptions import ObjectNotFoundError
from app.domain.enums import EnterpriseType


class FakeEnterprise:
    def __init__(
        self,
        enterprise_id,
        *,
        enterprise_type=EnterpriseType.DEPARTMENT,
        full_name="Производственное отделение",
        short_name="ПО",
        sap_code="SAP-001",
        deleted_at=None,
        updated_by=None,
    ):
        self.id = enterprise_id
        self.type = enterprise_type
        self.full_name = full_name
        self.short_name = short_name
        self.sap_code = sap_code
        self.deleted_at = deleted_at
        self.updated_by = updated_by


class FakeEnterpriseRepository:
    def __init__(self, enterprise=None):
        self.enterprise = enterprise
        self.received_id = None
        self.saved = None

    async def get_by_id(self, enterprise_id):
        self.received_id = enterprise_id
        return self.enterprise

    async def save(self, enterprise):
        self.saved = enterprise
        return enterprise


@pytest.mark.asyncio
async def test_get_department_returns_details():
    enterprise_id = uuid7()
    enterprise = FakeEnterprise(enterprise_id)
    repository = FakeEnterpriseRepository(enterprise)
    service = EnterpriseService(repository)

    result = await service.get_department(enterprise_id)

    assert result.id == enterprise_id
    assert result.full_name == "Производственное отделение"
    assert result.short_name == "ПО"
    assert result.sap_code == "SAP-001"
    assert repository.received_id == enterprise_id


@pytest.mark.asyncio
async def test_get_department_raises_when_missing():
    repository = FakeEnterpriseRepository()
    service = EnterpriseService(repository)

    with pytest.raises(ObjectNotFoundError):
        await service.get_department(uuid7())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enterprise_type",
    [EnterpriseType.HOLDING, EnterpriseType.BRANCH],
)
async def test_get_department_rejects_other_enterprise_types(enterprise_type):
    enterprise = FakeEnterprise(
        uuid7(),
        enterprise_type=enterprise_type,
    )
    service = EnterpriseService(FakeEnterpriseRepository(enterprise))

    with pytest.raises(ObjectNotFoundError):
        await service.get_department(enterprise.id)


@pytest.mark.asyncio
async def test_get_department_rejects_deleted_department():
    enterprise = FakeEnterprise(uuid7(), deleted_at=object())
    service = EnterpriseService(FakeEnterpriseRepository(enterprise))

    with pytest.raises(ObjectNotFoundError):
        await service.get_department(enterprise.id)


@pytest.mark.asyncio
async def test_update_department_updates_fields_and_audit_actor():
    actor_id = uuid7()
    enterprise = FakeEnterprise(uuid7())
    repository = FakeEnterpriseRepository(enterprise)
    service = EnterpriseService(repository)

    result = await service.update_department(
        enterprise.id,
        EnterpriseUpdate(
            full_name="Новое производственное отделение",
            short_name="Новое ПО",
            sap_code="SAP-002",
        ),
        actor_id=actor_id,
    )

    assert repository.saved is enterprise
    assert enterprise.full_name == "Новое производственное отделение"
    assert enterprise.short_name == "Новое ПО"
    assert enterprise.sap_code == "SAP-002"
    assert enterprise.updated_by == actor_id
    assert result.id == enterprise.id
    assert result.full_name == "Новое производственное отделение"


@pytest.mark.asyncio
async def test_update_department_raises_when_missing():
    service = EnterpriseService(FakeEnterpriseRepository())

    with pytest.raises(ObjectNotFoundError):
        await service.update_department(
            uuid7(),
            EnterpriseUpdate(
                full_name="Новое название",
                short_name="ПО",
            ),
            actor_id=uuid7(),
        )