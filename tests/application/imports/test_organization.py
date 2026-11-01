from datetime import UTC, datetime
from io import BytesIO
from uuid6 import uuid7

import pytest
from openpyxl import Workbook

from app.application.imports.organization import (
    HEADERS,
    SHEET_NAME,
    OrganizationImportService,
)
from app.domain.enums import EnterpriseType


class FakeEnterprise:
    def __init__(
        self,
        *,
        enterprise_id=None,
        enterprise_type=EnterpriseType.HOLDING,
        parent_id=None,
        full_name="Холдинг",
        short_name="Х",
        deleted_at=None,
    ):
        self.id = enterprise_id or uuid7()
        self.type = enterprise_type
        self.parent_id = parent_id
        self.full_name = full_name
        self.short_name = short_name
        self.deleted_at = deleted_at


class FakeRepository:
    def __init__(self, enterprises=None):
        self.enterprises = enterprises or []
        self.session = None

    async def get_all_for_access_scope(self):
        return self.enterprises


def make_xlsx(rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME

    worksheet.append(HEADERS)

    for row in rows:
        worksheet.append(row)

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    return content.getvalue()


def make_service(enterprises=None):
    return OrganizationImportService(
        FakeRepository(enterprises)
    )


@pytest.mark.asyncio
async def test_preview_creates_plan_for_new_organization():
    service = make_service()

    content = make_xlsx([
        [
            "Холдинг",
            "Х",
            "Филиал",
            "Ф",
            "Производственное отделение",
            "ПО",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is True
    assert result["summary"] == {
        "holdings": {"create": 1, "reuse": 0},
        "branches": {"create": 1, "reuse": 0},
        "departments": {"create": 1, "reuse": 0},
    }


@pytest.mark.asyncio
async def test_preview_reuses_existing_organization():
    holding = FakeEnterprise(
        enterprise_type=EnterpriseType.HOLDING,
        full_name="Холдинг",
        short_name="Х",
    )

    branch = FakeEnterprise(
        enterprise_type=EnterpriseType.BRANCH,
        parent_id=holding.id,
        full_name="Филиал",
        short_name="Ф",
    )

    department = FakeEnterprise(
        enterprise_type=EnterpriseType.DEPARTMENT,
        parent_id=branch.id,
        full_name="Производственное отделение",
        short_name="ПО",
    )

    service = make_service([holding, branch, department])

    content = make_xlsx([
        [
            "Холдинг",
            "Х",
            "Филиал",
            "Ф",
            "Производственное отделение",
            "ПО",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is True
    assert result["summary"] == {
        "holdings": {"create": 0, "reuse": 1},
        "branches": {"create": 0, "reuse": 1},
        "departments": {"create": 0, "reuse": 1},
    }


@pytest.mark.asyncio
async def test_preview_detects_short_name_conflict_in_database():
    holding = FakeEnterprise(
        full_name="Холдинг",
        short_name="Старое",
    )

    service = make_service([holding])

    content = make_xlsx([
        [
            "Холдинг",
            "Новое",
            "Филиал",
            "Ф",
            "ПО",
            "ПО",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is False
    assert result["summary"] is None
    assert any(
        "не совпадает" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_archived_enterprise():
    holding = FakeEnterprise(
        full_name="Холдинг",
        short_name="Х",
        deleted_at=datetime.now(UTC),
    )

    service = make_service([holding])

    content = make_xlsx([
        [
            "Холдинг",
            "Х",
            "Филиал",
            "Ф",
            "ПО",
            "ПО",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is False
    assert any(
        "архиве" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_different_short_names_inside_file():
    service = make_service()

    content = make_xlsx([
        [
            "Холдинг",
            "Х",
            "Филиал 1",
            "Ф1",
            "ПО 1",
            "ПО1",
        ],
        [
            "Холдинг",
            "Другое",
            "Филиал 2",
            "Ф2",
            "ПО 2",
            "ПО2",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is False
    assert any(
        "разные краткие наименования" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_allows_repeated_identical_rows():
    service = make_service()

    row = [
        "Холдинг",
        "Х",
        "Филиал",
        "Ф",
        "ПО",
        "ПО",
    ]

    content = make_xlsx([row, row])

    result = await service.preview(content)

    assert result["success"] is True
    assert result["summary"]["holdings"]["create"] == 1
    assert result["summary"]["branches"]["create"] == 1
    assert result["summary"]["departments"]["create"] == 1


@pytest.mark.asyncio
async def test_preview_rejects_missing_required_value():
    service = make_service()

    content = make_xlsx([
        [
            "Холдинг",
            "Х",
            "Филиал",
            "",
            "ПО",
            "ПО",
        ],
    ])

    result = await service.preview(content)

    assert result["success"] is False
    assert any(
        error.get("column") == HEADERS[3]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_wrong_headers():
    service = make_service()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(["Неверный заголовок", *HEADERS[1:]])

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    result = await service.preview(content.getvalue())

    assert result["success"] is False
    assert any(
        "Заголовки" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_more_than_500_data_rows():
    service = make_service()

    rows = [
        [
            f"Холдинг {index}",
            f"Х{index}",
            f"Филиал {index}",
            f"Ф{index}",
            f"ПО {index}",
            f"ПО{index}",
        ]
        for index in range(501)
    ]

    content = make_xlsx(rows)

    result = await service.preview(content)

    assert result["success"] is False
    assert any(
        "500 строк" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_rejects_invalid_file():
    service = make_service()

    result = await service.preview(b"not an xlsx file")

    assert result["success"] is False
    assert result["summary"] is None


@pytest.mark.asyncio
async def test_preview_rejects_wrong_sheet_name():
    service = make_service()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Лист1"
    worksheet.append(HEADERS)
    worksheet.append([
        "Холдинг",
        "Х",
        "Филиал",
        "Ф",
        "ПО",
        "ПО",
    ])

    content = BytesIO()
    workbook.save(content)
    workbook.close()

    result = await service.preview(content.getvalue())

    assert result["success"] is False
    assert any(
        SHEET_NAME in error["message"]
        for error in result["errors"]
    )


@pytest.mark.asyncio
async def test_preview_matches_short_name_without_case_sensitivity():
    holding = FakeEnterprise(
        full_name="Холдинг",
        short_name="Х",
    )

    service = make_service([holding])

    content = make_xlsx([[
        "Холдинг",
        "х",
        "Филиал",
        "Ф",
        "ПО",
        "ПО",
    ]])

    result = await service.preview(content)

    assert result["success"] is True
    assert result["summary"]["holdings"] == {
        "create": 0,
        "reuse": 1,
    }