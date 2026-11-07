from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from docx import Document
import pytest
from uuid6 import uuid7

from app.application.maintenance.service import TORecordService
from app.application.document_templates.service import (
    DocumentFormHierarchy,
    DocumentFormType,
    DocumentTemplateError,
    DocumentTemplateService,
    DocxProcessor,
)
from app.application.tree.schemas import (
    ConnectionTreeNode,
    EnterpriseTreeAncestor,
    EnterpriseTreeNode,
    SubstationTreeNode,
    URZATreeNode,
)
from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.maintenance import TORecord


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def access_service():
    service = MagicMock()
    service.can_access_urza = AsyncMock()
    service.can_modify_urza = AsyncMock(return_value=True)
    return service


@pytest.fixture
def task_repository():
    repository = MagicMock()
    repository.get_by_id = AsyncMock()
    return repository


@pytest.fixture
def service(repository, access_service, task_repository):
    return TORecordService(
        repository=repository,
        access_service=access_service,
        task_repository=task_repository,
    )


@pytest.mark.asyncio
async def test_get_by_urza_returns_records(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    records = [
        MagicMock(spec=TORecord),
        MagicMock(spec=TORecord),
    ]

    access_service.can_access_urza.return_value = True
    repository.get_by_urza_id = AsyncMock(
        return_value=records,
    )

    result = await service.get_by_urza(
        user_id,
        urza_id,
    )

    assert result == records
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_urza_id.assert_awaited_once_with(
        urza_id,
    )


@pytest.mark.asyncio
async def test_get_by_urza_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_urza_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_urza(
            user_id,
            urza_id,
        )

    repository.get_by_urza_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_approved_checks_access_and_returns_record(
    service, repository, access_service,
):
    user_id, urza_id = uuid7(), uuid7()
    record = MagicMock(spec=TORecord)
    access_service.can_access_urza.return_value = True
    repository.get_current_approved = AsyncMock(return_value=record)

    result = await service.get_current_approved(user_id, urza_id)

    assert result is record
    access_service.can_access_urza.assert_awaited_once_with(user_id, urza_id)
    repository.get_current_approved.assert_awaited_once_with(urza_id)


@pytest.mark.asyncio
async def test_get_current_approved_denies_without_access(
    service, repository, access_service,
):
    access_service.can_access_urza.return_value = False
    repository.get_current_approved = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_current_approved(uuid7(), uuid7())

    repository.get_current_approved.assert_not_awaited()


@pytest.mark.parametrize("form_type", list(DocumentFormType))
def test_runtime_template_generates_personalized_docx_without_changing_source(
    form_type, tmp_path,
):
    source = Path("data/document_templates") / f"{form_type.value}.docx"
    template_copy = tmp_path / source.name
    template_copy.write_bytes(source.read_bytes())
    hierarchy = DocumentFormHierarchy(
        holding="Холдинг А",
        branch="Филиал Б",
        production_department="ПО В",
        substation="ПС Г",
        connection="Присоединение Д",
        urza="УРЗА Е",
    )

    generated = DocumentTemplateService(None, tmp_path).create_document(
        form_type, hierarchy
    )
    try:
        document = Document(generated)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        text += "\n" + "\n".join(
            paragraph.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        )
        assert all(value in text for value in (
            "Холдинг А", "Филиал Б", "ПО В", "ПС Г", "Присоединение Д", "УРЗА Е"
        ))
        assert all(marker not in text for marker in hierarchy.marker_values())
        assert template_copy.read_bytes() == source.read_bytes()
        assert Path("docs", source.name).read_bytes() == source.read_bytes()
    finally:
        generated.unlink(missing_ok=True)


def test_docx_processor_replaces_split_runs_and_preserves_run_formatting():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("before ").bold = True
    placeholder = paragraph.add_run("$")
    placeholder.italic = True
    paragraph.add_run("холдинг")
    paragraph.add_run(" after")

    DocxProcessor.replace_markers(document, {"$холдинг": "Новое значение"})

    assert paragraph.text == "before Новое значение after"
    assert paragraph.runs[0].bold is True
    assert paragraph.runs[1].italic is True


def test_docx_processor_rejects_missing_required_marker():
    document = Document()
    document.add_paragraph("No placeholder here")
    with pytest.raises(DocumentTemplateError, match="missing required markers"):
        DocxProcessor.replace_markers(document, {"$холдинг": ""})


def test_docx_processor_replaces_markers_in_nested_tables_and_headers():
    document = Document()
    table = document.add_table(rows=1, cols=1)
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).paragraphs[0].add_run("$холдинг")
    document.sections[0].header.paragraphs[0].add_run("$филиал")

    DocxProcessor.replace_markers(document, {
        "$холдинг": "Холдинг", "$филиал": "Филиал"
    })

    assert nested.cell(0, 0).text == "Холдинг"
    assert document.sections[0].header.paragraphs[0].text == "Филиал"


def test_runtime_template_service_reports_missing_or_corrupt_templates(tmp_path):
    hierarchy = DocumentFormHierarchy()
    service = DocumentTemplateService(None, tmp_path)
    with pytest.raises(DocumentTemplateError, match="not found"):
        service.create_document(DocumentFormType.MAINTENANCE, hierarchy)

    (tmp_path / "maintenance.docx").write_bytes(b"not a docx")
    with pytest.raises(DocumentTemplateError, match="could not be processed"):
        service.create_document(DocumentFormType.MAINTENANCE, hierarchy)


def test_parallel_document_generations_use_distinct_temporary_files():
    from concurrent.futures import ThreadPoolExecutor

    service = DocumentTemplateService(None, Path("data/document_templates"))
    hierarchy = DocumentFormHierarchy(holding="Холдинг")
    with ThreadPoolExecutor(max_workers=4) as executor:
        paths = list(executor.map(
            lambda _: service.create_document(DocumentFormType.SETTINGS, hierarchy),
            range(4),
        ))
    try:
        assert len(set(paths)) == 4
        assert all(Document(path).paragraphs or Document(path).tables for path in paths)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_document_form_hierarchy_uses_tree_service_dtos():
    urza_id = uuid7()
    tree = [
        EnterpriseTreeNode(
            id=uuid7(), type="holding", full_name="Холдинг", short_name="Х",
            children=[
                EnterpriseTreeNode(
                    id=uuid7(), type="branch", full_name="Филиал", short_name="Ф",
                    children=[
                        EnterpriseTreeNode(
                            id=uuid7(), type="department", full_name="ПО", short_name="ПО",
                            substations=[
                                SubstationTreeNode(
                                    id=uuid7(), dispatch_name="ПС-1",
                                    connections=[
                                        ConnectionTreeNode(
                                            id=uuid7(), dispatch_name="ВЛ-1",
                                            urzas=[URZATreeNode(id=urza_id, dispatch_name="УРЗА-1")],
                                        )
                                    ],
                                )
                            ],
                        )
                    ],
                )
            ],
        )
    ]
    tree_service = MagicMock()
    tree_service.get_tree = AsyncMock(return_value=tree)
    user_id = uuid7()

    result = await DocumentTemplateService(tree_service, Path(".")).get_urza_hierarchy(
        user_id, urza_id
    )

    assert result == DocumentFormHierarchy(
        holding="Холдинг",
        branch="Филиал",
        production_department="ПО",
        substation="ПС-1",
        connection="ВЛ-1",
        urza="УРЗА-1",
    )
    tree_service.get_tree.assert_awaited_once_with(user_id=user_id, archive_only=False)


@pytest.mark.asyncio
async def test_department_scoped_tree_uses_typed_ancestor_names_without_substitution():
    urza_id = uuid7()
    tree_service = MagicMock()
    tree_service.get_tree = AsyncMock(return_value=[
        EnterpriseTreeNode(
            id=uuid7(),
            type="department",
            full_name="ПО Северное",
            short_name="ПО-С",
            ancestors=[
                EnterpriseTreeAncestor(
                    id=uuid7(), type="holding", full_name="Холдинг Север"
                ),
            ],
            substations=[SubstationTreeNode(
                id=uuid7(),
                dispatch_name="ПС Северная",
                connections=[ConnectionTreeNode(
                    id=uuid7(),
                    dispatch_name="ВЛ Северная",
                    urzas=[URZATreeNode(id=urza_id, dispatch_name="ДЗЛ Северная")],
                )],
            )],
        )
    ])

    hierarchy = await DocumentTemplateService(tree_service, Path(".")).get_urza_hierarchy(
        uuid7(), urza_id
    )

    assert hierarchy == DocumentFormHierarchy(
        holding="Холдинг Север",
        branch="",
        production_department="ПО Северное",
        substation="ПС Северная",
        connection="ВЛ Северная",
        urza="ДЗЛ Северная",
    )


@pytest.mark.asyncio
async def test_hierarchy_keeps_names_from_each_branch_and_department_separate():
    urza_one, urza_two = uuid7(), uuid7()
    holding = EnterpriseTreeAncestor(
        id=uuid7(), type="holding", full_name="Холдинг общий"
    )
    first = EnterpriseTreeNode(
        id=uuid7(),
        type="department",
        full_name="ПО Восточное",
        short_name="ПО-В",
        ancestors=[
            holding,
            EnterpriseTreeAncestor(
                id=uuid7(), type="branch", full_name="Филиал Восточный"
            ),
        ],
        substations=[SubstationTreeNode(
            id=uuid7(),
            dispatch_name="ПС Восточная",
            connections=[ConnectionTreeNode(
                id=uuid7(),
                dispatch_name="ВЛ Восточная",
                urzas=[URZATreeNode(id=urza_one, dispatch_name="Устройство 1")],
            )],
        )],
    )
    second = EnterpriseTreeNode(
        id=uuid7(),
        type="department",
        full_name="ПО Западное",
        short_name="ПО-З",
        ancestors=[
            holding,
            EnterpriseTreeAncestor(
                id=uuid7(), type="branch", full_name="Филиал Западный"
            ),
        ],
        substations=[SubstationTreeNode(
            id=uuid7(),
            dispatch_name="ПС Западная",
            connections=[ConnectionTreeNode(
                id=uuid7(),
                dispatch_name="ВЛ Западная",
                urzas=[URZATreeNode(id=urza_two, dispatch_name="Устройство 2")],
            )],
        )],
    )
    tree_service = MagicMock()
    tree_service.get_tree = AsyncMock(return_value=[first, second])
    service = DocumentTemplateService(tree_service, Path("."))

    east = await service.get_urza_hierarchy(uuid7(), urza_one)
    west = await service.get_urza_hierarchy(uuid7(), urza_two)

    assert (east.branch, east.production_department, east.urza) == (
        "Филиал Восточный", "ПО Восточное", "Устройство 1"
    )
    assert (west.branch, west.production_department, west.urza) == (
        "Филиал Западный", "ПО Западное", "Устройство 2"
    )


@pytest.mark.asyncio
async def test_unknown_urza_levels_are_empty_instead_of_reusing_other_names():
    tree_service = MagicMock()
    tree_service.get_tree = AsyncMock(return_value=[])

    hierarchy = await DocumentTemplateService(tree_service, Path(".")).get_urza_hierarchy(
        uuid7(), uuid7()
    )

    assert hierarchy == DocumentFormHierarchy()
    assert hierarchy.marker_values() == {
        "$холдинг": "",
        "$филиал": "",
        "$Название Производственного отделения": "",
        "$Название подстанции": "",
        "$Название присоединения": "",
        "$Название УРЗА": "",
    }


@pytest.mark.asyncio
async def test_get_by_task_returns_record(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    record = MagicMock(spec=TORecord)

    access_service.can_access_urza.return_value = True
    repository.get_by_task_id = AsyncMock(
        return_value=record,
    )

    result = await service.get_by_task(
        user_id,
        task_id,
        urza_id,
    )

    assert result is record
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_task_id.assert_awaited_once_with(
        task_id,
    )


@pytest.mark.asyncio
async def test_get_by_task_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_task_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_task(
            user_id,
            task_id,
            urza_id,
        )

    repository.get_by_task_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_returns_record(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    record = MagicMock(spec=TORecord)

    access_service.can_access_urza.return_value = True
    repository.get_by_id = AsyncMock(
        return_value=record,
    )

    result = await service.get_by_id(
        user_id,
        record_id,
        urza_id,
    )

    assert result is record
    access_service.can_access_urza.assert_awaited_once_with(
        user_id,
        urza_id,
    )
    repository.get_by_id.assert_awaited_once_with(
        record_id,
    )


@pytest.mark.asyncio
async def test_get_by_id_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    record_id = uuid7()

    access_service.can_access_urza.return_value = False
    repository.get_by_id = AsyncMock()

    with pytest.raises(PermissionError):
        await service.get_by_id(
            user_id,
            record_id,
            urza_id,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_requires_protocol_for_regular_maintenance(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    signed_form_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    with pytest.raises(
        ValueError,
        match="требуется протокол",
    ):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.V,
            signed_form_file_id=signed_form_file_id,
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_requires_signed_form_for_every_maintenance_type(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    with pytest.raises(ValueError, match="подписанной формы"):
        await service.create(
            user_id=uuid7(),
            urza_id=uuid7(),
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.TK,
            signed_form_file_id=None,
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_allows_maintenance_without_protocol_for_tk(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()
    signed_form_file_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=signed_form_file_id,
    )

    assert isinstance(result, TORecord)
    assert result.maintenance_type == MaintenanceType.TK
    assert result.scan_protocol_id is None
    assert result.signed_form_file_id == signed_form_file_id

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "maintenance_type",
    [
        MaintenanceType.O,
        MaintenanceType.OSM,
    ],
)
async def test_create_allows_maintenance_without_protocol_for_special_types(
    service,
    repository,
    access_service,
    maintenance_type,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=maintenance_type,
        signed_form_file_id=uuid7(),
    )

    assert isinstance(result, TORecord)
    assert result.maintenance_type == maintenance_type
    assert result.scan_protocol_id is None

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_saves_protocol_and_task(
    service,
    repository,
    access_service,
    task_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    scan_protocol_id = uuid7()
    editable_protocol_id = uuid7()
    signed_form_file_id = uuid7()
    task_id = uuid7()

    access_service.can_access_urza.return_value = True
    task_repository.get_by_id.return_value = SimpleNamespace(
        id=task_id,
        deleted_at=None,
        work_type=TaskWorkType.MAINTENANCE,
        urza_id=urza_id,
        assigned_to=user_id,
        status=TaskStatus.IN_PROGRESS,
    )
    repository.get_by_task_id = AsyncMock(return_value=None)
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.K,
        signed_form_file_id=signed_form_file_id,
        scan_protocol_id=scan_protocol_id,
        editable_protocol_id=editable_protocol_id,
        task_id=task_id,
    )

    assert result.urza_id == urza_id
    assert result.maintenance_type == MaintenanceType.K
    assert result.scan_protocol_id == scan_protocol_id
    assert result.editable_protocol_id == editable_protocol_id
    assert result.signed_form_file_id == signed_form_file_id
    assert result.task_id == task_id
    assert result.created_by == user_id
    assert result.updated_by == user_id

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_rejects_task_not_assigned_to_user(
    service,
    repository,
    access_service,
    task_repository,
):
    user_id = uuid7()
    urza_id = uuid7()
    task_id = uuid7()
    access_service.can_access_urza.return_value = True
    task_repository.get_by_id.return_value = SimpleNamespace(
        id=task_id,
        deleted_at=None,
        work_type=TaskWorkType.MAINTENANCE,
        urza_id=urza_id,
        assigned_to=uuid7(),
        status=TaskStatus.IN_PROGRESS,
    )

    with pytest.raises(PermissionError, match="назначенный исполнитель"):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.K,
            signed_form_file_id=uuid7(),
            scan_protocol_id=uuid7(),
            task_id=task_id,
        )

    repository.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_uses_default_values(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=uuid7(),
        urza_id=uuid7(),
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=uuid7(),
    )

    assert result.detected_deviations == "Не выявлено"
    assert result.measures_taken == "Не требуется"

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_denies_access(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = False
    access_service.can_modify_urza.return_value = False
    repository.add = AsyncMock()

    with pytest.raises(PermissionError):
        await service.create(
            user_id=user_id,
            urza_id=urza_id,
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.TK,
            signed_form_file_id=uuid7(),
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_saves_historical_data(
    service,
    repository,
    access_service,
):
    user_id = uuid7()
    urza_id = uuid7()

    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=user_id,
        urza_id=urza_id,
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=uuid7(),
        historical_data=True,
    )

    assert result.historical_data is True

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_uses_default_historical_data(
    service,
    repository,
    access_service,
):
    access_service.can_access_urza.return_value = True
    repository.add = AsyncMock()

    result = await service.create(
        user_id=uuid7(),
        urza_id=uuid7(),
        maintenance_date=date(2026, 9, 17),
        maintenance_type=MaintenanceType.TK,
        signed_form_file_id=uuid7(),
    )

    assert result.historical_data is False

    repository.add.assert_awaited_once_with(result)
