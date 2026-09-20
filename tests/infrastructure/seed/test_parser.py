from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import (
    ElementBase,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.infrastructure.seed.parser import CSVRowParser


def test_optional_string() -> None:
    assert CSVRowParser.optional_string(" Test ") == "Test"
    assert CSVRowParser.optional_string("") is None
    assert CSVRowParser.optional_string("   ") is None


def test_boolean() -> None:
    assert CSVRowParser.boolean("да") is True
    assert CSVRowParser.boolean(" нет ") is False


def test_boolean_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Некорректное логическое значение"):
        CSVRowParser.boolean("yes")


def test_date() -> None:
    assert CSVRowParser.date("2026-08-20") == date(2026, 8, 20)


def test_date_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Некорректная дата"):
        CSVRowParser.date("20.08.2026")


def test_decimal() -> None:
    assert CSVRowParser.decimal("56.123456") == Decimal("56.123456")
    assert CSVRowParser.decimal("") is None


def test_enums() -> None:
    assert CSVRowParser.highest_voltage("110") == HighestVoltage.KV_110
    assert (
        CSVRowParser.operational_current_type("permanent")
        == OperationalCurrentType.PERMANENT
    )
    assert CSVRowParser.urza_status("in_operation") == URZAStatus.IN_OPERATION
    assert (
        CSVRowParser.element_base("microprocessor")
        == ElementBase.MICROPROCESSOR
    )
    assert CSVRowParser.urza_category("IV") == URZACategory.IV
    assert CSVRowParser.room_category("II") == RoomCategory.II


def test_invalid_enum_rejected() -> None:
    with pytest.raises(ValueError, match="Некорректное напряжение"):
        CSVRowParser.highest_voltage("999")