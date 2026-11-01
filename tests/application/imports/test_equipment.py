
from datetime import date, datetime, UTC
from io import BytesIO
from types import SimpleNamespace
from uuid6 import uuid7

import pytest
from openpyxl import Workbook
from openpyxl.comments import Comment

from app.application.imports import equipment as equipment_module
from app.application.imports.equipment import (
    HEADERS,
    SHEET_NAME,
    EquipmentImportService,
)
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


class FakeEnterprise:
    def __init__(
        self,
        *,
        enterprise_id=None,
        enterprise_type=EnterpriseType.HOLDING,
        parent_id=None,
        full_name="Холдинг",
        deleted_at=None,
    ):
        self.id = enterprise_id or uuid7()
        self.type = enterprise_type
        self.parent_id = parent_id
        self.full_name = full_name
        self.deleted_at = deleted_at


class FakeUser:
    def __init__(
        self,
        *,
        role=UserRole.SUPERADMIN,
        enterprise_id=None,
        active=True,
        deleted_at=None,
    ):
        self.id = uuid7()
        self.role = role
        self.enterprise_id = enterprise_id
        self.active = active
        self.deleted_at = deleted_at


class FakeUserRepository:
    def __init__(self, user):
        self.user = user

    async def get_by_id(self, user_id):
        return self.user if self.user and self.user.id == user_id else None


class FakeEnterpriseRepository:
    def __init__(self, enterprises):
        self.enterprises = enterprises

    async def get_all_for_access_scope(self):
        return self.enterprises

    async def get_by_id(self, enterprise_id):
        return next(
            (item for item in self.enterprises if item.id == enterprise_id),
            None,
        )


class FakeSubstationRepository:
    def __init__(self, substations=None):
        self.substations = substations or []
        self.requested_enterprise_ids = None
        self.include_archived = None

    async def get_by_enterprise_ids(
        self,
        enterprise_ids,
        *,
        include_archived=False,
    ):
        self.requested_enterprise_ids = enterprise_ids
        self.include_archived = include_archived

        return [
            item
            for item in self.substations
            if item.enterprise_id in enterprise_ids
        ]


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1


def make_xlsx(rows, *, sheet_name=SHEET_NAME):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name

    worksheet.append(HEADERS)

    for row in rows:
        worksheet.append(row)

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    return content.getvalue()


def make_row(
    *,
    holding="Холдинг",
    branch="Филиал",
    department="ПО",
    substation="ПС 110 кВ",
    voltage="110",
    current_type="Переменный ток",
    substation_sap=None,
    substation_asureo=None,
    address=None,
    latitude=None,
    longitude=None,
    connection="ВЛ 110 кВ",
    connection_sap=None,
    connection_asureo=None,
    connection_rdu="Да",
    urza="ДЗШ",
    urza_rdu="Да",
    inventory_number="123",
    commissioning_date=None,
    status="В эксплуатации",
    element_base="Микропроцессорная",
    category="II",
    room_category="I",
    complexity="Нет",
):
    if commissioning_date is None:
        commissioning_date = date(2020, 1, 15)

    return [
        holding,
        branch,
        department,
        substation,
        voltage,
        current_type,
        substation_sap,
        substation_asureo,
        address,
        latitude,
        longitude,
        connection,
        connection_sap,
        connection_asureo,
        connection_rdu,
        urza,
        urza_rdu,
        inventory_number,
        commissioning_date,
        status,
        element_base,
        category,
        room_category,
        complexity,
    ]


def make_enterprises():
    holding = FakeEnterprise(
        enterprise_type=EnterpriseType.HOLDING,
        full_name="Холдинг",
    )
    branch = FakeEnterprise(
        enterprise_type=EnterpriseType.BRANCH,
        parent_id=holding.id,
        full_name="Филиал",
    )
    department = FakeEnterprise(
        enterprise_type=EnterpriseType.DEPARTMENT,
        parent_id=branch.id,
        full_name="ПО",
    )

    return holding, branch, department


def make_service(monkeypatch, *, user=None, enterprises=None, substations=None):
    session = FakeSession()
    user = user or FakeUser()
    enterprises = enterprises if enterprises is not None else list(make_enterprises())

    enterprise_repository = FakeEnterpriseRepository(enterprises)
    substation_repository = FakeSubstationRepository(substations)

    monkeypatch.setattr(
        equipment_module,
        "EnterpriseRepository",
        lambda session: enterprise_repository,
    )
    monkeypatch.setattr(
        equipment_module,
        "SubstationRepository",
        lambda session: substation_repository,
    )
    monkeypatch.setattr(
        equipment_module,
        "ConnectionRepository",
        lambda session: SimpleNamespace(),
    )
    monkeypatch.setattr(
        equipment_module,
        "URZARepository",
        lambda session: SimpleNamespace(),
    )

    access_service = SimpleNamespace(
        user_repository=FakeUserRepository(user),
    )

    service = EquipmentImportService(session, access_service)
    return service, user, enterprises, substation_repository, session


@pytest.mark.asyncio
async def test_preview_accepts_valid_equipment_file(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row()]),
        user.id,
    )

    assert result["success"] is True
    assert result["errors"] == []
    assert result["summary"] == {
        "substations": 1,
        "connections": 1,
        "urzas": 1,
    }


@pytest.mark.asyncio
async def test_preview_accepts_connection_without_urza(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    row = make_row(
        urza=None,
        urza_rdu=None,
        inventory_number=None,
        commissioning_date=None,
        status=None,
        element_base=None,
        category=None,
        room_category=None,
        complexity=None,
    )

    row[18] = None

    result = await service.preview(make_xlsx([row]), user.id)

    assert result["success"] is True
    assert result["summary"]["urzas"] == 0


@pytest.mark.asyncio
async def test_preview_rejects_empty_file(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(b"", user.id)

    assert result["success"] is False
    assert result["summary"] is None
    assert any("пуст" in error["message"].lower() for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_invalid_xlsx(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(b"not an xlsx file", user.id)

    assert result["success"] is False
    assert result["summary"] is None


@pytest.mark.asyncio
async def test_preview_rejects_wrong_sheet_name(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row()], sheet_name="Лист1"),
        user.id,
    )

    assert result["success"] is False
    assert any("называться" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_wrong_headers(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(["Неверный заголовок", *HEADERS[1:]])

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    result = await service.preview(content.getvalue(), user.id)

    assert result["success"] is False
    assert any("Заголовки" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_missing_required_value(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    row = make_row()
    row[3] = None

    result = await service.preview(make_xlsx([row]), user.id)

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[3]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_invalid_voltage(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row(voltage="999")]),
        user.id,
    )

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[4]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_invalid_boolean(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row(connection_rdu="Возможно")]),
        user.id,
    )

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[14]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_invalid_commissioning_date(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row(commissioning_date="15.01.2020")]),
        user.id,
    )

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[18]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_only_one_coordinate(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    result = await service.preview(
        make_xlsx([make_row(latitude=55.75, longitude=None)]),
        user.id,
    )

    assert result["success"] is False
    assert sum(
        error.get("column") in {HEADERS[9], HEADERS[10]}
        for error in result["errors"]
    ) == 2


@pytest.mark.asyncio
async def test_preview_rejects_urza_fields_without_urza_name(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    row = make_row(urza=None)
    row[16] = "Да"

    result = await service.preview(make_xlsx([row]), user.id)

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[16]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_comment_in_cell(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(HEADERS)
    worksheet.append(make_row())
    worksheet["D2"].comment = Comment("Комментарий", "tester")

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    result = await service.preview(content.getvalue(), user.id)

    assert result["success"] is False
    assert any(
        "запрещённые объекты" in error["message"].lower()
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_formula(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    row = make_row()
    row[3] = "=1+1"

    result = await service.preview(make_xlsx([row]), user.id)

    assert result["success"] is False
    assert any("Формулы" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_data_outside_table(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(HEADERS)
    worksheet.append(make_row())
    worksheet["Y2"] = "Лишние данные"

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    result = await service.preview(content.getvalue(), user.id)

    assert result["success"] is False
    assert any("за пределами таблицы" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_inactive_user(monkeypatch):
    user = FakeUser(active=False)
    service, *_ = make_service(monkeypatch, user=user)

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert any("неактивен" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_user_without_import_role(monkeypatch):
    user = FakeUser(role=UserRole.SPECIALIST)
    service, *_ = make_service(monkeypatch, user=user)

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert any("только ADMIN и SUPERADMIN" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_admin_import_to_another_department(monkeypatch):
    enterprises = list(make_enterprises())
    other_department = FakeEnterprise(
        enterprise_type=EnterpriseType.DEPARTMENT,
        parent_id=enterprises[1].id,
        full_name="Другое ПО",
    )
    user = FakeUser(
        role=UserRole.ADMIN,
        enterprise_id=other_department.id,
    )
    service, *_ = make_service(
        monkeypatch,
        user=user,
        enterprises=[*enterprises, other_department],
    )

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert any("только в своё ПО" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_missing_holding(monkeypatch):
    service, user, *_ = make_service(monkeypatch, enterprises=[])

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert any("Холдинг" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_archived_holding(monkeypatch):
    holding, branch, department = make_enterprises()
    holding.deleted_at = datetime.now(UTC)

    service, user, *_ = make_service(
        monkeypatch,
        enterprises=[holding, branch, department],
    )

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert any("архивирован" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_groups_multiple_connections_under_one_substation(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    first = make_row(connection="ВЛ 1")
    second = make_row(connection="ВЛ 2", urza="ДЗШ 2")

    result = await service.preview(make_xlsx([first, second]), user.id)

    assert result["success"] is True
    assert result["summary"] == {
        "substations": 1,
        "connections": 2,
        "urzas": 2,
    }


@pytest.mark.asyncio
async def test_preview_groups_repeated_identical_rows(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    row = make_row()

    result = await service.preview(make_xlsx([row, row]), user.id)

    assert result["success"] is True
    assert result["summary"] == {
        "substations": 1,
        "connections": 1,
        "urzas": 1,
    }


@pytest.mark.asyncio
async def test_preview_rejects_conflicting_substation_attributes(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    first = make_row()
    second = make_row(voltage="220")

    result = await service.preview(make_xlsx([first, second]), user.id)

    assert result["success"] is False
    assert any("противоречивые характеристики" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_conflicting_connection_attributes(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    first = make_row()
    second = make_row(connection_rdu="Нет")

    result = await service.preview(make_xlsx([first, second]), user.id)

    assert result["success"] is False
    assert any("противоречивые характеристики" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_conflicting_urza_attributes(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    first = make_row()
    second = make_row(complexity="Да")

    result = await service.preview(make_xlsx([first, second]), user.id)

    assert result["success"] is False
    assert any("противоречивые характеристики" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_rejects_existing_substation_including_archived(monkeypatch):
    holding, branch, department = make_enterprises()

    existing = SimpleNamespace(
        enterprise_id=department.id,
        dispatch_name="ПС 110 кВ",
    )

    service, user, _, repository, _ = make_service(
        monkeypatch,
        enterprises=[holding, branch, department],
        substations=[existing],
    )

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is False
    assert repository.include_archived is True
    assert any("уже существует" in error["message"] for error in result["errors"])


@pytest.mark.asyncio
async def test_preview_does_not_write_to_session(monkeypatch):
    service, user, *_, session = make_service(monkeypatch)

    result = await service.preview(make_xlsx([make_row()]), user.id)

    assert result["success"] is True
    assert session.added == []
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_preview_accepts_all_supported_voltage_values(monkeypatch):
    service, user, *_ = make_service(monkeypatch)

    for value, expected in (
        ("500", HighestVoltage.KV_500),
        ("220", HighestVoltage.KV_220),
        ("110", HighestVoltage.KV_110),
        ("35", HighestVoltage.KV_35),
        ("10", HighestVoltage.KV_10),
        ("6", HighestVoltage.KV_6),
        ("0.4", HighestVoltage.KV_0_4),
        ("0,4", HighestVoltage.KV_0_4),
    ):
        result = await service.preview(
            make_xlsx([make_row(voltage=value)]),
            user.id,
        )

        assert result["success"] is True, (value, result["errors"])
