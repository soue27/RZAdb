from datetime import date
from decimal import Decimal

from app.domain.enums import (
    ElementBase,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)


class CSVRowParser:
    """Преобразует строковые значения CSV в типы доменной модели."""

    @staticmethod
    def optional_string(value: str) -> str | None:
        value = value.strip()
        return value or None

    @staticmethod
    def boolean(value: str) -> bool:
        normalized = value.strip().lower()

        if normalized == "да":
            return True

        if normalized == "нет":
            return False

        raise ValueError(
            f"Некорректное логическое значение: {value!r}. "
            "Ожидалось 'да' или 'нет'."
        )

    @staticmethod
    def date(value: str) -> date:
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная дата: {value!r}. "
                "Ожидался формат YYYY-MM-DD."
            ) from exc

    @staticmethod
    def decimal(value: str) -> Decimal | None:
        value = value.strip()

        if not value:
            return None

        try:
            return Decimal(value)
        except ArithmeticError as exc:
            raise ValueError(
                f"Некорректное десятичное число: {value!r}."
            ) from exc

    @staticmethod
    def highest_voltage(value: str) -> HighestVoltage:
        try:
            return HighestVoltage(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректное напряжение: {value!r}."
            ) from exc

    @staticmethod
    def operational_current_type(value: str) -> OperationalCurrentType:
        try:
            return OperationalCurrentType(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректный тип оперативного тока: {value!r}."
            ) from exc

    @staticmethod
    def urza_status(value: str) -> URZAStatus:
        try:
            return URZAStatus(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректный статус УРЗА: {value!r}."
            ) from exc

    @staticmethod
    def element_base(value: str) -> ElementBase:
        try:
            return ElementBase(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная элементная база: {value!r}."
            ) from exc

    @staticmethod
    def urza_category(value: str) -> URZACategory:
        try:
            return URZACategory(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная категория УРЗА: {value!r}."
            ) from exc

    @staticmethod
    def room_category(value: str) -> RoomCategory:
        try:
            return RoomCategory(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная категория помещения: {value!r}."
            ) from exc