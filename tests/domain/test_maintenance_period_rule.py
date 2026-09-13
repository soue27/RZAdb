from app.domain.maintenance_period_rule import MaintenancePeriodRule


def test_maintenance_period_rule_model() -> None:
    rule = MaintenancePeriodRule()

    assert rule.__tablename__ == "maintenance_period_rules"

    assert rule.__table__.c.id.primary_key is True
    assert rule.__table__.c.room_category.nullable is False
    assert rule.__table__.c.element_base.nullable is False
    assert rule.__table__.c.maintenance_period_years.nullable is False

    constraints = rule.__table__.constraints

    assert any(
        constraint.name == "uq_maintenance_period_rule_category_element"
        for constraint in constraints
    )