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
        """Очищает строковое значение и преобразует пустую строку в None.

        Args:
            value: Исходное значение.

        Returns:
            Очищенная строка или None.
        """
        value = value.strip()
        return value or None

    @staticmethod
    def boolean(value: str) -> bool:
        """Преобразует русское значение «да»/«нет» в bool.

        Args:
            value: Строковое значение CSV.

        Returns:
            True для «да», False для «нет».

        Raises:
            ValueError: Если значение не соответствует ожидаемым вариантам.
        """
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
        """Преобразует строку ISO-даты в datetime.date.

        Args:
            value: Дата в формате YYYY-MM-DD.

        Returns:
            Объект date.

        Raises:
            ValueError: Если строка не содержит корректную ISO-дату.
        """
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная дата: {value!r}. "
                "Ожидался формат YYYY-MM-DD."
            ) from exc

    @staticmethod
    def decimal(value: str) -> Decimal | None:
        """Преобразует строку в Decimal; пустое значение возвращает как None.

        Args:
            value: Исходная строка.

        Returns:
            Decimal или None.

        Raises:
            ValueError: Если значение не является десятичным числом.
        """
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
        """Преобразует строку в допустимый класс высшего напряжения.

        Args:
            value: Значение напряжения.

        Returns:
            Элемент HighestVoltage.

        Raises:
            ValueError: Если напряжение не входит в доменный перечень.
        """
        try:
            return HighestVoltage(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректное напряжение: {value!r}."
            ) from exc

    @staticmethod
    def operational_current_type(value: str) -> OperationalCurrentType:
        """Преобразует строку в тип оперативного тока.

        Args:
            value: Значение из CSV.

        Returns:
            Элемент OperationalCurrentType.

        Raises:
            ValueError: Если тип тока не поддерживается.
        """
        try:
            return OperationalCurrentType(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректный тип оперативного тока: {value!r}."
            ) from exc

    @staticmethod
    def urza_status(value: str) -> URZAStatus:
        """Преобразует строку в эксплуатационный статус УРЗА.

        Args:
            value: Значение из CSV.

        Returns:
            Элемент URZAStatus.

        Raises:
            ValueError: Если статус не поддерживается.
        """
        try:
            return URZAStatus(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректный статус УРЗА: {value!r}."
            ) from exc

    @staticmethod
    def element_base(value: str) -> ElementBase:
        """Преобразует строку в тип элементной базы УРЗА.

        Args:
            value: Значение из CSV.

        Returns:
            Элемент ElementBase.

        Raises:
            ValueError: Если элементная база не поддерживается.
        """
        try:
            return ElementBase(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная элементная база: {value!r}."
            ) from exc

    @staticmethod
    def urza_category(value: str) -> URZACategory:
        """Преобразует строку в категорию устройства РЗА.

        Args:
            value: Значение из CSV.

        Returns:
            Элемент URZACategory.

        Raises:
            ValueError: Если категория не поддерживается.
        """
        try:
            return URZACategory(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная категория УРЗА: {value!r}."
            ) from exc

    @staticmethod
    def room_category(value: str) -> RoomCategory:
        """Преобразует строку в категорию помещения.

        Args:
            value: Значение из CSV.

        Returns:
            Элемент RoomCategory.

        Raises:
            ValueError: Если категория не поддерживается.
        """
        try:
            return RoomCategory(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Некорректная категория помещения: {value!r}."
            ) from exc