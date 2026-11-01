import re
from collections import defaultdict
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import text

from app.application.enterprises.repository import EnterpriseRepository
from app.domain.enterprise import Enterprise
from app.domain.enums import EnterpriseType


MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_DATA_ROWS = 500
MAX_UNCOMPRESSED_SIZE = 30 * 1024 * 1024
MAX_ARCHIVE_FILES = 100

HEADERS = (
    "Холдинг",
    "Краткое наименование холдинга",
    "Филиал",
    "Краткое наименование филиала",
    "ПО",
    "Краткое наименование ПО",
)

LEVELS = (
    EnterpriseType.HOLDING,
    EnterpriseType.BRANCH,
    EnterpriseType.DEPARTMENT,
)

FORBIDDEN_PARTS = (
    "xl/externalLinks/",
    "xl/embeddings/",
    "xl/activeX/",
    "xl/ctrlProps/",
    "xl/drawings/",
    "xl/threadedComments/",
    "xl/persons/",
    "customXml/",
)


class OrganizationImportService:
    """Импорт организационной структуры из XLSX."""

    def __init__(self, repository: EnterpriseRepository) -> None:
        self.repository = repository

    async def preview(self, content: bytes) -> dict:
        """Проверяет файл и возвращает сводку без изменения БД."""

        rows, errors = self._read_rows(content)

        if errors:
            return self._failure(errors)

        enterprises = await self.repository.get_all_for_access_scope()
        plan, errors = self._build_plan(rows, enterprises)

        if errors:
            return self._failure(errors)

        return {
            "success": True,
            "summary": self._make_summary(plan),
            "errors": [],
        }

    async def confirm(
        self,
        content: bytes,
        *,
        actor_id,
    ) -> dict:
        """Повторно проверяет файл и создаёт предприятия одной транзакцией."""

        rows, errors = self._read_rows(content)

        if errors:
            return self._failure(errors)

        enterprises = await self.repository.get_all_for_access_scope()
        plan, errors = self._build_plan(rows, enterprises)

        if errors:
            return self._failure(errors)

        created = {
            EnterpriseType.HOLDING: 0,
            EnterpriseType.BRANCH: 0,
            EnterpriseType.DEPARTMENT: 0,
        }

        # Создаём предприятия последовательно по уровням.
        # После flush родитель получает UUID, доступный дочерним записям.
        for level in LEVELS:
            pending = []

            for item in plan[level]:
                if item["enterprise"] is not None:
                    continue

                parent = item["parent"]

                if parent is None:
                    parent_id = None
                elif isinstance(parent, Enterprise):
                    parent_id = parent.id
                else:
                    parent_id = parent["enterprise"].id

                enterprise = Enterprise(
                    type=level,
                    parent_id=parent_id,
                    full_name=item["full_name"],
                    short_name=item["short_name"],
                    created_by=actor_id,
                    updated_by=actor_id,
                )

                self.repository.session.add(enterprise)

                item["enterprise"] = enterprise
                pending.append(enterprise)

            if pending:
                await self.repository.session.flush()
                created[level] = len(pending)

        return {
            "success": True,
            "created": {
                "holdings": created[EnterpriseType.HOLDING],
                "branches": created[EnterpriseType.BRANCH],
                "departments": created[EnterpriseType.DEPARTMENT],
            },
            "errors": [],
        }

    def _read_rows(
        self,
        content: bytes,
    ) -> tuple[list[dict], list[dict]]:
        """Проверяет XLSX и извлекает строки организационной структуры."""

        if not content:
            return [], [{"message": "Файл пуст."}]

        if len(content) > MAX_FILE_SIZE:
            return [], [{"message": "Размер файла превышает 5 МБ."}]

        try:
            with ZipFile(BytesIO(content)) as archive:
                files = archive.infolist()

                if len(files) > MAX_ARCHIVE_FILES:
                    return [], [{
                        "message": "Файл содержит слишком много внутренних элементов.",
                    }]

                if sum(item.file_size for item in files) > MAX_UNCOMPRESSED_SIZE:
                    return [], [{
                        "message": "Внутренний размер XLSX превышает допустимый предел.",
                    }]

                if any(item.flag_bits & 0x1 for item in files):
                    return [], [{
                        "message": "Зашифрованные элементы XLSX запрещены.",
                    }]

                names = archive.namelist()

                if any(
                    name.startswith(FORBIDDEN_PARTS)
                    or name.endswith("vbaProject.bin")
                    or name.startswith("xl/comments")
                    for name in names
                ):
                    return [], [{
                        "message": (
                            "Файл содержит запрещённые объекты "
                            "(макросы, комментарии, рисунки или встроенные элементы)."
                        ),
                    }]

        except (BadZipFile, OSError, ValueError):
            return [], [{
                "message": "Файл не является корректным XLSX.",
            }]

        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=False,
                data_only=False,
            )
        except Exception:
            return [], [{
                "message": "Не удалось прочитать XLSX-файл.",
            }]

        try:
            return self._extract_rows(workbook)

        finally:
            workbook.close()

    def _extract_rows(self, workbook) -> tuple[list[dict], list[dict]]:
        errors: list[dict] = []

        if len(workbook.worksheets) != 1:
            return [], [{
                "message": "В файле должен быть ровно один лист.",
            }]

        if len(workbook.defined_names):
            return [], [{
                "message": "Именованные диапазоны в файле запрещены.",
            }]

        if getattr(workbook, "_external_links", []):
            return [], [{
                "message": "Внешние ссылки в файле запрещены.",
            }]

        if workbook.security.lockStructure:
            return [], [{
                "message": "Защита структуры книги запрещена.",
            }]

        worksheet = workbook.worksheets[0]

        if worksheet.sheet_state != "visible":
            return [], [{
                "message": "Скрытые листы запрещены.",
            }]

        if worksheet.protection.sheet:
            return [], [{
                "message": "Защита листа запрещена.",
            }]

        if worksheet.merged_cells.ranges:
            return [], [{
                "message": "Объединённые ячейки запрещены.",
            }]

        if worksheet._images or worksheet._charts:
            return [], [{
                "message": "Изображения и диаграммы запрещены.",
            }]

        if any(
            dimension.hidden
            for dimension in worksheet.row_dimensions.values()
        ):
            return [], [{
                "message": "Скрытые строки запрещены.",
            }]

        if any(
            dimension.hidden
            for dimension in worksheet.column_dimensions.values()
        ):
            return [], [{
                "message": "Скрытые столбцы запрещены.",
            }]

        # Проверяем все ячейки, включая находящиеся за пределами таблицы.
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.comment is not None:
                    errors.append({
                        "row": cell.row,
                        "column": cell.column_letter,
                        "message": "Комментарии в ячейках запрещены.",
                    })

                if cell.hyperlink is not None:
                    errors.append({
                        "row": cell.row,
                        "column": cell.column_letter,
                        "message": "Гиперссылки в ячейках запрещены.",
                    })

                if cell.data_type == "f":
                    errors.append({
                        "row": cell.row,
                        "column": cell.column_letter,
                        "message": "Формулы в ячейках запрещены.",
                    })

                if (
                    cell.column > len(HEADERS)
                    and self._has_value(cell.value)
                ):
                    errors.append({
                        "row": cell.row,
                        "column": cell.column_letter,
                        "message": "Данные за пределами таблицы запрещены.",
                    })

        if errors:
            return [], errors

        actual_headers = tuple(
            worksheet.cell(row=1, column=column).value
            for column in range(1, len(HEADERS) + 1)
        )

        if actual_headers != HEADERS:
            return [], [{
                "row": 1,
                "message": (
                    "Заголовки не соответствуют шаблону. "
                    "Проверьте названия и порядок шести столбцов."
                ),
            }]

        rows = []

        for row_number in range(2, worksheet.max_row + 1):
            values = [
                worksheet.cell(row=row_number, column=column).value
                for column in range(1, len(HEADERS) + 1)
            ]

            # Пустые строки внутри таблицы игнорируются.
            if not any(self._has_value(value) for value in values):
                continue

            if len(rows) >= MAX_DATA_ROWS:
                errors.append({
                    "row": row_number,
                    "message": "В файле превышен лимит: максимум 500 строк данных.",
                })
                break

            normalized_values = []

            for column_number, value in enumerate(values):
                column_name = HEADERS[column_number]

                if not isinstance(value, str):
                    errors.append({
                        "row": row_number,
                        "column": column_name,
                        "message": "Значение должно быть текстом.",
                    })
                    normalized_values.append("")
                    continue

                value = value.strip()
                normalized_values.append(value)

                if not value:
                    errors.append({
                        "row": row_number,
                        "column": column_name,
                        "message": "Поле обязательно для заполнения.",
                    })
                elif len(value) > 255:
                    errors.append({
                        "row": row_number,
                        "column": column_name,
                        "message": "Длина значения не должна превышать 255 символов.",
                    })

            rows.append({
                "row": row_number,
                "values": normalized_values,
            })

        if not rows and not errors:
            errors.append({
                "message": "В файле отсутствуют строки для импорта.",
            })

        return rows, errors

    def _build_plan(
            self,
            rows: list[dict],
            enterprises: list[Enterprise],
    ) -> tuple[dict, list[dict]]:
        """Сопоставляет данные XLSX с БД и строит план импорта."""

        errors: list[dict] = []

        nodes = {
            level: {}
            for level in LEVELS
        }

        # 1. Формируем уникальные узлы из строк XLSX.
        for row in rows:
            (
                holding_name,
                holding_short,
                branch_name,
                branch_short,
                department_name,
                department_short,
            ) = row["values"]

            holding_key = self._node_key(
                EnterpriseType.HOLDING,
                None,
                holding_name,
            )

            branch_key = self._node_key(
                EnterpriseType.BRANCH,
                holding_key,
                branch_name,
            )

            department_key = self._node_key(
                EnterpriseType.DEPARTMENT,
                branch_key,
                department_name,
            )

            row_nodes = (
                (
                    EnterpriseType.HOLDING,
                    holding_key,
                    holding_name,
                    holding_short,
                    None,
                ),
                (
                    EnterpriseType.BRANCH,
                    branch_key,
                    branch_name,
                    branch_short,
                    holding_key,
                ),
                (
                    EnterpriseType.DEPARTMENT,
                    department_key,
                    department_name,
                    department_short,
                    branch_key,
                ),
            )

            for level, key, full_name, short_name, parent_key in row_nodes:
                existing = nodes[level].get(key)

                if existing is None:
                    nodes[level][key] = {
                        "key": key,
                        "full_name": full_name,
                        "short_name": short_name,
                        "parent_key": parent_key,
                        "rows": [row["row"]],
                    }
                    continue

                existing["rows"].append(row["row"])

                if existing["short_name"] != short_name:
                    errors.append({
                        "row": row["row"],
                        "column": self._short_column(level),
                        "message": (
                            f"Для предприятия «{full_name}» указаны "
                            "разные краткие наименования в файле."
                        ),
                    })

        if errors:
            return {}, errors

        # 2. Индексируем существующие предприятия, включая архивные.
        by_parent_and_name = defaultdict(list)
        by_name = defaultdict(list)

        for enterprise in enterprises:
            normalized_name = self._normalize(enterprise.full_name)

            by_parent_and_name[
                (enterprise.parent_id, normalized_name)
            ].append(enterprise)

            by_name[normalized_name].append(enterprise)

        plan = {
            level: []
            for level in LEVELS
        }

        # Здесь хранятся уже сопоставленные узлы:
        # Enterprise — найденная запись БД;
        # dict — новый узел, который будет создан.
        resolved = {}

        # 3. Сопоставляем последовательно: холдинги, филиалы, ПО.
        for level in LEVELS:
            for node in nodes[level].values():
                parent_key = node["parent_key"]

                if parent_key is None:
                    parent = None

                    # Холдинг ищем по всей оргструктуре.
                    matches = by_name[
                        self._normalize(node["full_name"])
                    ]

                else:
                    # Если родитель не прошёл проверку, дочерний узел
                    # также не может быть корректно сопоставлен.
                    if parent_key not in resolved:
                        continue

                    parent = resolved[parent_key]

                    if isinstance(parent, Enterprise):
                        # Родитель уже существует в БД.
                        matches = by_parent_and_name[
                            (
                                parent.id,
                                self._normalize(node["full_name"]),
                            )
                        ]
                    else:
                        # Новый родитель ещё не существует в БД.
                        # Его дочерние предприятия также будут новыми.
                        matches = []

                # 4. Проверяем неоднозначность.
                if len(matches) > 1:
                    errors.append({
                        "row": node["rows"][0],
                        "column": self._full_column(level),
                        "message": (
                            f"Найдено несколько предприятий "
                            f"с наименованием «{node['full_name']}» "
                            "в одной области уникальности."
                        ),
                    })
                    continue

                enterprise = matches[0] if matches else None

                # 5. Проверяем найденную запись.
                if enterprise is not None:
                    if enterprise.deleted_at is not None:
                        errors.append({
                            "row": node["rows"][0],
                            "column": self._full_column(level),
                            "message": (
                                f"Предприятие «{node['full_name']}» "
                                "уже существует в архиве. Импорт отклонён."
                            ),
                        })
                        continue

                    if enterprise.type != level:
                        errors.append({
                            "row": node["rows"][0],
                            "column": self._full_column(level),
                            "message": (
                                f"У предприятия «{node['full_name']}» "
                                "в БД указан неправильный тип "
                                "или нарушена иерархия."
                            ),
                        })
                        continue

                    if level == EnterpriseType.HOLDING:
                        if enterprise.parent_id is not None:
                            errors.append({
                                "row": node["rows"][0],
                                "column": self._full_column(level),
                                "message": (
                                    f"Холдинг «{node['full_name']}» "
                                    "имеет родительское предприятие в БД."
                                ),
                            })
                            continue

                    if enterprise.short_name.strip() != node["short_name"]:
                        errors.append({
                            "row": node["rows"][0],
                            "column": self._short_column(level),
                            "message": (
                                f"Краткое наименование предприятия "
                                f"«{node['full_name']}» не совпадает: "
                                f"в БД — «{enterprise.short_name}», "
                                f"в Excel — «{node['short_name']}»."
                            ),
                        })
                        continue

                # 6. Добавляем узел в план.
                node["enterprise"] = enterprise
                node["parent"] = parent

                plan[level].append(node)

                resolved[node["key"]] = (
                    enterprise if enterprise is not None else node
                )

        return plan, errors

    @staticmethod
    def _make_summary(plan: dict) -> dict:
        return {
            "holdings": OrganizationImportService._level_summary(
                plan[EnterpriseType.HOLDING]
            ),
            "branches": OrganizationImportService._level_summary(
                plan[EnterpriseType.BRANCH]
            ),
            "departments": OrganizationImportService._level_summary(
                plan[EnterpriseType.DEPARTMENT]
            ),
        }

    @staticmethod
    def _level_summary(items: list[dict]) -> dict:
        return {
            "create": sum(
                item["enterprise"] is None
                for item in items
            ),
            "reuse": sum(
                item["enterprise"] is not None
                for item in items
            ),
        }

    @staticmethod
    def _failure(errors: list[dict]) -> dict:
        return {
            "success": False,
            "summary": None,
            "errors": errors,
        }

    @staticmethod
    def _node_key(
        level: EnterpriseType,
        parent_key: tuple | None,
        full_name: str,
    ) -> tuple:
        return (
            level,
            parent_key,
            OrganizationImportService._normalize(full_name),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    @staticmethod
    def _has_value(value) -> bool:
        return value is not None and (
            not isinstance(value, str) or bool(value.strip())
        )

    @staticmethod
    def _full_column(level: EnterpriseType) -> str:
        return {
            EnterpriseType.HOLDING: HEADERS[0],
            EnterpriseType.BRANCH: HEADERS[2],
            EnterpriseType.DEPARTMENT: HEADERS[4],
        }[level]

    @staticmethod
    def _short_column(level: EnterpriseType) -> str:
        return {
            EnterpriseType.HOLDING: HEADERS[1],
            EnterpriseType.BRANCH: HEADERS[3],
            EnterpriseType.DEPARTMENT: HEADERS[5],
        }[level]