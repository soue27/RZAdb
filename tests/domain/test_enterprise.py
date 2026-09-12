from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


def test_enterprise_model() -> None:
    enterprise = Enterprise(
        type=EnterpriseType.HOLDING,
        full_name="Тестовый холдинг",
        short_name="Тест",
    )

    assert enterprise.type == EnterpriseType.HOLDING
    assert enterprise.full_name == "Тестовый холдинг"
    assert enterprise.short_name == "Тест"
    assert enterprise.parent_id is None
    assert enterprise.sap_code is None
    assert enterprise.sap_code is None