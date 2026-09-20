import csv
from pathlib import Path
from typing import ClassVar


class CSVImporter:
    """Читает и валидирует CSV с тестовыми данными РЗА."""

    REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "holding_full_name",
        "holding_short_name",
        "branch_full_name",
        "branch_short_name",
        "department_full_name",
        "department_short_name",
        "substation_dispatch_name",
        "substation_highest_voltage",
        "connection_dispatch_name",
        "connection_rdu_subordination",
        "operational_current_type",
        "urza_dispatch_name",
        "urza_rdu_subordination",
        "urza_commissioning_date",
        "urza_status",
        "urza_element_base",
        "urza_category",
        "urza_room_category",
        "urza_complexity",
    }

    def __init__(self, path: Path) -> None:
        self.path = path

    def read_rows(self) -> list[dict[str, str]]:
        """Читает строки CSV и проверяет наличие обязательных колонок."""

        with self.path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            if reader.fieldnames is None:
                raise ValueError("CSV-файл не содержит заголовок.")

            columns = set(reader.fieldnames)
            missing_columns = self.REQUIRED_COLUMNS - columns

            if missing_columns:
                missing = ", ".join(sorted(missing_columns))
                raise ValueError(
                    f"В CSV отсутствуют обязательные колонки: {missing}"
                )

            return list(reader)