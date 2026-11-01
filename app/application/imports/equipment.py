# app/application/imports/equipment.py

import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from sqlalchemy import select

from app.application.access.service import AccessService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.objects.owner_lock import lock_owner_row
from app.application.substations.repository import SubstationRepository
from app.application.urzas.repository import URZARepository
from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
    UserRole,
)
from app.domain.substation import Substation
from app.domain.urza import URZA


MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_DATA_ROWS = 10_000
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
MAX_ARCHIVE_FILES = 200

SHEET_NAME = "Оборудование"

HEADERS = (
    "Холдинг",
    "Филиал",
    "ПО",
    "Подстанция",
    "Наибольшее напряжение",
    "Тип оперативного тока",
    "SAP-код ПС",
    "ASUREO-код ПС",
    "Адрес ПС",
    "Широта",
    "Долгота",
    "Присоединение",
    "SAP-код присоединения",
    "ASUREO-код присоединения",
    "Подчинение РДУ (присоединение)",
    "УРЗА",
    "Подчинение РДУ (УРЗА)",
    "Инвентарный номер",
    "Дата ввода в эксплуатацию",
    "Статус УРЗА",
    "Элементная база",
    "Категория УРЗА",
    "Категория помещения",
    "Сложность УРЗА",
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

VOLTAGE_VALUES = {
    "500": HighestVoltage.KV_500,
    "220": HighestVoltage.KV_220,
    "110": HighestVoltage.KV_110,
    "35": HighestVoltage.KV_35,
    "10": HighestVoltage.KV_10,
    "6": HighestVoltage.KV_6,
    "0.4": HighestVoltage.KV_0_4,
    "0,4": HighestVoltage.KV_0_4,
    "0,4 кв": HighestVoltage.KV_0_4,
    "0.4 кв": HighestVoltage.KV_0_4,
}

ENUM_VALUES = {
    OperationalCurrentType: {
        "постоянный ток": OperationalCurrentType.PERMANENT,
        "выпрямленный ток": OperationalCurrentType.RECTIFIED,
        "переменный ток": OperationalCurrentType.ALTERNATING,
    },
    URZAStatus: {
        "в эксплуатации": URZAStatus.IN_OPERATION,
        "в ремонте": URZAStatus.IN_REPAIR,
        "выведено из эксплуатации": URZAStatus.DECOMMISSIONED,
        "резерв": URZAStatus.RESERVE,
    },
    ElementBase: {
        "электромеханическая": ElementBase.ELECTROMECHANICAL,
        "микроэлектронная": ElementBase.MICROELECTRONIC,
        "микропроцессорная": ElementBase.MICROPROCESSOR,
    },
    URZACategory: {
        "i": URZACategory.I,
        "ii": URZACategory.II,
        "iii": URZACategory.III,
        "iv": URZACategory.IV,
    },
    RoomCategory: {
        "i": RoomCategory.I,
        "ii": RoomCategory.II,
        "iii": RoomCategory.III,
    },
}

STRING_LIMITS = {
    4: 255,
    6: 64,
    7: 64,
    8: 500,
    11: 255,
    12: 64,
    13: 64,
    15: 255,
    17: 64,
}


class EquipmentImportService:
    """Предварительная проверка и импорт оборудования из XLSX."""

    def __init__(
        self,
        session,
        access_service: AccessService,
    ) -> None:
        self.session = session
        self.access_service = access_service

        self.enterprise_repository = EnterpriseRepository(session)
        self.substation_repository = SubstationRepository(session)
        self.connection_repository = ConnectionRepository(session)
        self.urza_repository = URZARepository(session)

    async def preview(self, content: bytes, actor_id) -> dict:
        """Проверяет файл и права, не изменяя БД."""

        rows, errors = self._read_rows(content)

        if errors:
            return self._failure(errors)

        actor, errors = await self._get_actor(actor_id)

        if errors:
            return self._failure(errors)

        enterprises = await self.enterprise_repository.get_all_for_access_scope()

        plan, errors = self._build_plan(rows, enterprises, actor)

        if errors:
            return self._failure(errors)

        existing = await self._check_existing_substations(plan)

        if existing:
            return self._failure(existing)

        return {
            "success": True,
            "summary": self._make_summary(plan),
            "errors": [],
        }

    async def confirm(self, content: bytes, actor_id) -> dict:
        """
        Повторно проверяет файл и создаёт оборудование.

        Commit выполняется внешним get_session.
        """

        rows, errors = self._read_rows(content)

        if errors:
            return self._failure(errors)

        actor, errors = await self._get_actor(actor_id)

        if errors:
            return self._failure(errors)

        enterprises = await self.enterprise_repository.get_all_for_access_scope()

        plan, errors = self._build_plan(rows, enterprises, actor)

        if errors:
            return self._failure(errors)

        department_ids = sorted(
            {
                item["department"].id
                for item in plan
            },
            key=str,
        )

        # Блокируем ПО в одинаковом порядке, чтобы снизить вероятность deadlock.
        for department_id in department_ids:
            locked = await lock_owner_row(
                self.session,
                Enterprise,
                department_id,
            )

            if locked is None or locked.deleted_at is not None:
                return self._failure([
                    self._error(
                        message=(
                            "ПО было удалено или изменено после предварительной "
                            "проверки. Загрузите файл повторно."
                        ),
                    )
                ])

            if locked.type is not EnterpriseType.DEPARTMENT:
                return self._failure([
                    self._error(
                        message="Нарушена иерархия организационной структуры.",
                    )
                ])

        # Повторная проверка после получения блокировок.
        existing = await self._check_existing_substations(plan)

        if existing:
            return self._failure(existing)

        created_substations = 0
        created_connections = 0
        created_urzas = 0

        for item in plan:
            substation_data = item["substation"]

            substation = Substation(
                enterprise_id=item["department"].id,
                dispatch_name=substation_data["name"],
                highest_voltage=substation_data["highest_voltage"],
                operational_current_type=substation_data[
                    "operational_current_type"
                ],
                sap_code=substation_data["sap_code"],
                asureo_code=substation_data["asureo_code"],
                address=substation_data["address"],
                latitude=substation_data["latitude"],
                longitude=substation_data["longitude"],
                created_by=actor_id,
                updated_by=actor_id,
            )

            self.session.add(substation)
            await self.session.flush()
            created_substations += 1

            for connection_data in item["connections"].values():
                connection = Connection(
                    substation_id=substation.id,
                    dispatch_name=connection_data["name"],
                    sap_code=connection_data["sap_code"],
                    asureo_code=connection_data["asureo_code"],
                    rdu_subordination=connection_data["rdu_subordination"],
                    created_by=actor_id,
                    updated_by=actor_id,
                )

                self.session.add(connection)
                await self.session.flush()
                created_connections += 1

                for urza_data in connection_data["urzas"].values():
                    urza = URZA(
                        connection_id=connection.id,
                        dispatch_name=urza_data["name"],
                        rdu_subordination=urza_data["rdu_subordination"],
                        inventory_number=urza_data["inventory_number"],
                        commissioning_date=urza_data["commissioning_date"],
                        status=urza_data["status"],
                        element_base=urza_data["element_base"],
                        category=urza_data["category"],
                        room_category=urza_data["room_category"],
                        complexity=urza_data["complexity"],
                        created_by=actor_id,
                        updated_by=actor_id,
                    )

                    self.session.add(urza)
                    created_urzas += 1

        await self.session.flush()

        return {
            "success": True,
            "created": {
                "substations": created_substations,
                "connections": created_connections,
                "urzas": created_urzas,
            },
            "errors": [],
        }

    async def _get_actor(self, actor_id):
        user = await self.access_service.user_repository.get_by_id(actor_id)

        if user is None or not user.active or user.deleted_at is not None:
            return None, [
                self._error(message="Пользователь не найден или неактивен.")
            ]

        if user.role not in {UserRole.SUPERADMIN, UserRole.ADMIN}:
            return None, [
                self._error(
                    message="Импорт оборудования доступен только ADMIN и SUPERADMIN."
                )
            ]

        if user.role is UserRole.ADMIN:
            if user.enterprise_id is None:
                return None, [
                    self._error(
                        message="Для ADMIN не определено предприятие доступа."
                    )
                ]

            department = await self.enterprise_repository.get_by_id(
                user.enterprise_id
            )

            if (
                department is None
                or department.deleted_at is not None
                or department.type is not EnterpriseType.DEPARTMENT
            ):
                return None, [
                    self._error(
                        message="ADMIN должен быть привязан к действующему ПО."
                    )
                ]

        return user, []

    def _read_rows(self, content: bytes) -> tuple[list[dict], list[dict]]:
        if not content:
            return [], [self._error(message="Файл пуст.")]

        if len(content) > MAX_FILE_SIZE:
            return [], [self._error(message="Размер файла превышает 5 МБ.")]

        try:
            with ZipFile(BytesIO(content)) as archive:
                files = archive.infolist()

                if len(files) > MAX_ARCHIVE_FILES:
                    return [], [
                        self._error(
                            message="Файл содержит слишком много внутренних элементов."
                        )
                    ]

                if sum(item.file_size for item in files) > MAX_UNCOMPRESSED_SIZE:
                    return [], [
                        self._error(
                            message="Внутренний размер XLSX превышает допустимый предел."
                        )
                    ]

                if any(item.flag_bits & 0x1 for item in files):
                    return [], [
                        self._error(message="Зашифрованные элементы XLSX запрещены.")
                    ]

                names = archive.namelist()

                if any(
                    name.startswith(FORBIDDEN_PARTS)
                    or name.endswith("vbaProject.bin")
                    or name.startswith("xl/comments")
                    for name in names
                ):
                    return [], [
                        self._error(
                            message=(
                                "Файл содержит запрещённые объекты: "
                                "макросы, комментарии, рисунки или вложения."
                            )
                        )
                    ]

        except (BadZipFile, OSError, ValueError):
            return [], [
                self._error(message="Файл не является корректным XLSX.")
            ]

        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=False,
                data_only=False,
            )
        except (InvalidFileException, OSError, ValueError, BadZipFile):
            return [], [
                self._error(message="Не удалось прочитать XLSX-файл.")
            ]

        try:
            return self._extract_rows(workbook)
        finally:
            workbook.close()

    def _extract_rows(self, workbook) -> tuple[list[dict], list[dict]]:
        if len(workbook.worksheets) != 1:
            return [], [
                self._error(message="В книге должен быть ровно один лист.")
            ]

        if workbook.sheetnames != [SHEET_NAME]:
            return [], [
                self._error(
                    message=f"Единственный лист должен называться «{SHEET_NAME}»."
                )
            ]

        if len(workbook.defined_names):
            return [], [
                self._error(message="Именованные диапазоны запрещены.")
            ]

        if getattr(workbook, "_external_links", []):
            return [], [
                self._error(message="Внешние ссылки запрещены.")
            ]

        if workbook.security.lockStructure:
            return [], [
                self._error(message="Защита структуры книги запрещена.")
            ]

        worksheet = workbook.worksheets[0]

        if worksheet.sheet_state != "visible":
            return [], [
                self._error(message="Скрытые листы запрещены.")
            ]

        if worksheet.protection.sheet:
            return [], [
                self._error(message="Защита листа запрещена.")
            ]

        if worksheet.merged_cells.ranges:
            return [], [
                self._error(message="Объединённые ячейки запрещены.")
            ]

        if worksheet._images or worksheet._charts:
            return [], [
                self._error(message="Изображения и диаграммы запрещены.")
            ]

        if any(dimension.hidden for dimension in worksheet.row_dimensions.values()):
            return [], [
                self._error(message="Скрытые строки запрещены.")
            ]

        if any(
            dimension.hidden
            for dimension in worksheet.column_dimensions.values()
        ):
            return [], [
                self._error(message="Скрытые столбцы запрещены.")
            ]

        errors = []

        for row in worksheet.iter_rows():
            for cell in row:
                if cell.comment is not None:
                    errors.append(
                        self._error(
                            row=cell.row,
                            column=cell.column_letter,
                            message="Комментарии в ячейках запрещены.",
                        )
                    )

                if cell.hyperlink is not None:
                    errors.append(
                        self._error(
                            row=cell.row,
                            column=cell.column_letter,
                            message="Гиперссылки запрещены.",
                        )
                    )

                if cell.data_type == "f":
                    errors.append(
                        self._error(
                            row=cell.row,
                            column=cell.column_letter,
                            message="Формулы запрещены.",
                        )
                    )

                if cell.column > len(HEADERS) and self._has_value(cell.value):
                    errors.append(
                        self._error(
                            row=cell.row,
                            column=cell.column_letter,
                            message="Данные за пределами таблицы запрещены.",
                        )
                    )

        if errors:
            return [], errors

        actual_headers = tuple(
            worksheet.cell(row=1, column=index).value
            for index in range(1, len(HEADERS) + 1)
        )

        if actual_headers != HEADERS:
            return [], [
                self._error(
                    row=1,
                    message="Заголовки не совпадают с утверждённым шаблоном.",
                    expected=list(HEADERS),
                    actual=list(actual_headers),
                )
            ]

        rows = []
        errors = []

        for row_number in range(2, worksheet.max_row + 1):
            values = [
                worksheet.cell(row=row_number, column=index).value
                for index in range(1, len(HEADERS) + 1)
            ]

            if not any(self._has_value(value) for value in values):
                continue

            if len(rows) >= MAX_DATA_ROWS:
                errors.append(
                    self._error(
                        row=row_number,
                        message="Превышен лимит: максимум 10 000 строк данных.",
                    )
                )
                break

            parsed, row_errors = self._parse_row(row_number, values)
            rows.append(parsed)
            errors.extend(row_errors)

        if not rows and not errors:
            errors.append(
                self._error(message="В файле отсутствуют строки для импорта.")
            )

        return rows, errors

    def _parse_row(self, row_number: int, values: list) -> tuple[dict, list[dict]]:
        errors = []

        def report(index: int, message: str):
            errors.append(
                self._error(
                    row=row_number,
                    column=HEADERS[index],
                    message=message,
                )
            )

        def string(index: int, *, required=False, limit=None):
            value = values[index]

            if value is None:
                result = None
            elif isinstance(value, str):
                result = value.strip() or None
            else:
                report(index, "Ожидается текстовое значение.")
                return None

            if required and result is None:
                report(index, "Поле обязательно для заполнения.")

            if result is not None and limit and len(result) > limit:
                report(index, f"Максимальная длина — {limit} символов.")

            return result

        def boolean(index: int, *, required=False):
            value = string(index)

            if value is None:
                if required:
                    report(index, "Поле обязательно для заполнения.")
                return None

            normalized = self._normalize(value)

            if normalized == "да":
                return True
            if normalized == "нет":
                return False

            report(index, "Допустимые значения: «Да» или «Нет».")
            return None

        def enum_value(index: int, enum_class, *, required=False):
            value = string(index)

            if value is None:
                if required:
                    report(index, "Поле обязательно для заполнения.")
                return None

            normalized = self._normalize(value)

            if enum_class is HighestVoltage:
                result = VOLTAGE_VALUES.get(normalized)
            else:
                result = ENUM_VALUES[enum_class].get(normalized)

            if result is None:
                allowed = (
                    [item.value for item in HighestVoltage]
                    if enum_class is HighestVoltage
                    else list(ENUM_VALUES[enum_class])
                )
                report(
                    index,
                    f"Недопустимое значение. Допустимые варианты: {allowed}.",
                )

            return result

        holding = string(0, required=True, limit=255)
        branch = string(1, required=True, limit=255)
        department = string(2, required=True, limit=255)
        substation_name = string(3, required=True, limit=255)

        highest_voltage = enum_value(4, HighestVoltage, required=True)
        operational_current_type = enum_value(
            5,
            OperationalCurrentType,
            required=True,
        )

        substation_sap = string(6, limit=64)
        substation_asureo = string(7, limit=64)
        address = string(8, limit=500)

        latitude = self._decimal_value(values[9], 9, report)
        longitude = self._decimal_value(values[10], 10, report)

        if (latitude is None) != (longitude is None):
            report(9, "Широта и долгота должны быть заполнены одновременно.")
            report(10, "Широта и долгота должны быть заполнены одновременно.")

        connection_name = string(11, required=True, limit=255)
        connection_sap = string(12, limit=64)
        connection_asureo = string(13, limit=64)
        connection_rdu = boolean(14, required=True)

        urza_name = string(15, limit=255)

        urza_fields = values[16:24]
        has_urza_data = any(self._has_value(value) for value in urza_fields)

        urza_data = None

        if urza_name is None:
            if has_urza_data:
                for index in range(16, 24):
                    if self._has_value(values[index]):
                        report(
                            index,
                            "Поле УРЗА должно быть заполнено, если указаны её характеристики.",
                        )
        else:
            urza_rdu = boolean(16, required=True)
            inventory_number = string(17, limit=64)

            commissioning_date = values[18]
            if isinstance(commissioning_date, datetime):
                commissioning_date = commissioning_date.date()

            if not isinstance(commissioning_date, date):
                report(
                    18,
                    "Укажите дату Excel, а не текст. Формат отображения — ДД.ММ.ГГГГ.",
                )
                commissioning_date = None

            status = enum_value(19, URZAStatus, required=True)
            element_base = enum_value(20, ElementBase, required=True)
            category = enum_value(21, URZACategory, required=True)
            room_category = enum_value(22, RoomCategory, required=True)
            complexity = boolean(23, required=True)

            urza_data = {
                "name": urza_name,
                "rdu_subordination": urza_rdu,
                "inventory_number": inventory_number,
                "commissioning_date": commissioning_date,
                "status": status,
                "element_base": element_base,
                "category": category,
                "room_category": room_category,
                "complexity": complexity,
            }

        return {
            "row": row_number,
            "holding": holding,
            "branch": branch,
            "department": department,
            "substation": {
                "name": substation_name,
                "highest_voltage": highest_voltage,
                "operational_current_type": operational_current_type,
                "sap_code": substation_sap,
                "asureo_code": substation_asureo,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
            },
            "connection": {
                "name": connection_name,
                "sap_code": connection_sap,
                "asureo_code": connection_asureo,
                "rdu_subordination": connection_rdu,
            },
            "urza": urza_data,
        }, errors

    def _build_plan(
        self,
        rows: list[dict],
        enterprises: list[Enterprise],
        actor,
    ) -> tuple[list[dict], list[dict]]:
        errors = []

        enterprise_index = defaultdict(list)

        for enterprise in enterprises:
            enterprise_index[
                (enterprise.parent_id, self._normalize(enterprise.full_name))
            ].append(enterprise)

        plan_by_substation = {}

        for row in rows:
            holding_matches = enterprise_index[
                (None, self._normalize(row["holding"]))
            ]

            if len(holding_matches) != 1:
                errors.append(
                    self._row_error(
                        row,
                        0,
                        (
                            f"Холдинг «{row['holding']}» "
                            + (
                                "не найден."
                                if not holding_matches
                                else "найден неоднозначно."
                            )
                        ),
                    )
                )
                continue

            holding = holding_matches[0]

            if holding.deleted_at is not None or holding.type is not EnterpriseType.HOLDING:
                errors.append(
                    self._row_error(row, 0, "Холдинг архивирован или имеет неверный тип.")
                )
                continue

            branch_matches = enterprise_index[
                (holding.id, self._normalize(row["branch"]))
            ]

            if len(branch_matches) != 1:
                errors.append(
                    self._row_error(
                        row,
                        1,
                        (
                            f"Филиал «{row['branch']}» "
                            + (
                                "не найден в указанном холдинге."
                                if not branch_matches
                                else "найден неоднозначно."
                            )
                        ),
                    )
                )
                continue

            branch = branch_matches[0]

            if branch.deleted_at is not None or branch.type is not EnterpriseType.BRANCH:
                errors.append(
                    self._row_error(row, 1, "Филиал архивирован или имеет неверный тип.")
                )
                continue

            department_matches = enterprise_index[
                (branch.id, self._normalize(row["department"]))
            ]

            if len(department_matches) != 1:
                errors.append(
                    self._row_error(
                        row,
                        2,
                        (
                            f"ПО «{row['department']}» "
                            + (
                                "не найдено в указанном филиале."
                                if not department_matches
                                else "найдено неоднозначно."
                            )
                        ),
                    )
                )
                continue

            department = department_matches[0]

            if (
                department.deleted_at is not None
                or department.type is not EnterpriseType.DEPARTMENT
            ):
                errors.append(
                    self._row_error(row, 2, "ПО архивировано или имеет неверный тип.")
                )
                continue

            if actor.role is UserRole.ADMIN and actor.enterprise_id != department.id:
                errors.append(
                    self._row_error(
                        row,
                        2,
                        "ADMIN может импортировать оборудование только в своё ПО.",
                    )
                )
                continue

            substation = row["substation"]
            substation_key = (
                department.id,
                self._normalize(substation["name"]),
            )

            item = plan_by_substation.get(substation_key)

            if item is None:
                item = {
                    "department": department,
                    "substation": substation,
                    "connections": {},
                    "rows": [row["row"]],
                }
                plan_by_substation[substation_key] = item
            else:
                item["rows"].append(row["row"])

                if not self._same_substation(item["substation"], substation):
                    errors.append(
                        self._row_error(
                            row,
                            3,
                            (
                                "Для одной подстанции указаны противоречивые "
                                "характеристики."
                            ),
                        )
                    )
                    continue

            connection = row["connection"]
            connection_key = self._normalize(connection["name"])

            connection_item = item["connections"].get(connection_key)

            if connection_item is None:
                connection_item = {
                    **connection,
                    "urzas": {},
                    "rows": [row["row"]],
                }
                item["connections"][connection_key] = connection_item
            else:
                connection_item["rows"].append(row["row"])

                if not self._same_connection(connection_item, connection):
                    errors.append(
                        self._row_error(
                            row,
                            11,
                            "Для одного присоединения указаны противоречивые характеристики.",
                        )
                    )
                    continue

            urza = row["urza"]

            if urza is not None:
                urza_key = self._normalize(urza["name"])
                previous = connection_item["urzas"].get(urza_key)

                if previous is None:
                    connection_item["urzas"][urza_key] = urza
                elif previous != urza:
                    errors.append(
                        self._row_error(
                            row,
                            15,
                            "Для одной УРЗА указаны противоречивые характеристики.",
                        )
                    )

        if errors:
            return [], errors

        return list(plan_by_substation.values()), []

    async def _check_existing_substations(self, plan: list[dict]) -> list[dict]:
        department_ids = {item["department"].id for item in plan}

        existing = await self.substation_repository.get_by_enterprise_ids(
            department_ids,
            include_archived=True,
        )

        existing_index = defaultdict(list)

        for substation in existing:
            existing_index[
                (
                    substation.enterprise_id,
                    self._normalize(substation.dispatch_name),
                )
            ].append(substation)

        errors = []

        for item in plan:
            key = (
                item["department"].id,
                self._normalize(item["substation"]["name"]),
            )

            matches = existing_index[key]

            if matches:
                errors.append(
                    self._error(
                        row=item["rows"][0],
                        column=HEADERS[3],
                        context={
                            "ПО": item["department"].full_name,
                            "Подстанция": item["substation"]["name"],
                        },
                        message=(
                            "Подстанция с таким нормализованным наименованием "
                            "уже существует в этом ПО. Дополнение существующей "
                            "подстанции запрещено."
                        ),
                    )
                )

        return errors

    @staticmethod
    def _same_substation(left: dict, right: dict) -> bool:
        fields = (
            "highest_voltage",
            "operational_current_type",
            "sap_code",
            "asureo_code",
            "address",
            "latitude",
            "longitude",
        )
        return all(left[field] == right[field] for field in fields)

    @staticmethod
    def _same_connection(left: dict, right: dict) -> bool:
        fields = (
            "sap_code",
            "asureo_code",
            "rdu_subordination",
        )
        return all(left[field] == right[field] for field in fields)

    @staticmethod
    def _make_summary(plan: list[dict]) -> dict:
        connections = [
            connection
            for item in plan
            for connection in item["connections"].values()
        ]

        return {
            "substations": len(plan),
            "connections": len(connections),
            "urzas": sum(len(item["urzas"]) for item in connections),
        }

    @staticmethod
    def _decimal_value(value, index: int, report):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None

        if isinstance(value, bool):
            report(index, "Ожидается числовое значение.")
            return None

        try:
            if isinstance(value, str):
                value = value.strip().replace(",", ".")
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            report(index, "Ожидается корректное числовое значение.")
            return None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    @staticmethod
    def _has_value(value) -> bool:
        return value is not None and (
            not isinstance(value, str) or bool(value.strip())
        )

    @staticmethod
    def _error(
        message: str,
        *,
        row=None,
        column=None,
        context=None,
        expected=None,
        actual=None,
    ) -> dict:
        result = {"message": message}

        if row is not None:
            result["row"] = row
        if column is not None:
            result["column"] = column
        if context is not None:
            result["context"] = context
        if expected is not None:
            result["expected"] = expected
        if actual is not None:
            result["actual"] = actual

        return result

    def _row_error(self, row: dict, index: int, message: str) -> dict:
        return self._error(
            row=row["row"],
            column=HEADERS[index],
            context={
                "Холдинг": row["holding"],
                "Филиал": row["branch"],
                "ПО": row["department"],
                "Подстанция": row["substation"]["name"],
                "Присоединение": row["connection"]["name"],
            },
            message=message,
        )

    def _failure(self, errors: list[dict]) -> dict:
        return {
            "success": False,
            "summary": None,
            "errors": errors,
        }