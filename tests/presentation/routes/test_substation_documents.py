from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.rza_instructions.service import RZAInstructionService
from app.domain.enums import UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_rza_instruction_service,
    get_selectivity_scheme_service,
    get_task_repository,
    get_task_service,
    get_tree_service,
)


class _Objects:
    async def get_object(
        self,
        *,
        user_id,
        object_type,
        object_id,
        **kwargs,
    ):
        return SimpleNamespace(
            id=object_id,
            name="ПС",
            object_type=object_type,
        )


class _Files:
    def __init__(self):
        self.discarded = []
        self.archived = []

    async def upload(self, **kwargs):
        return SimpleNamespace(id=uuid7(), s3_key="test.pdf")

    async def archive(self, **kwargs):
        self.archived.append(kwargs)

    async def discard_upload(self, file):
        self.discarded.append(file)

class _SchemeService:
    def __init__(self, error=None):
        self.create_kwargs = None
        self.error = error

    async def create(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.create_kwargs = kwargs
        return SimpleNamespace(id=uuid7())


class _TransitionService:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def submit_for_review(self, *args):
        self.calls.append(("submit", args))
        if self.error:
            raise self.error

    async def review(self, *args, **kwargs):
        self.calls.append(("review", args, kwargs))
        if self.error:
            raise self.error


class _Tree:
    async def get_tree(self, *, user_id):
        return []


class _InstructionService:
    def __init__(self, version):
        self.version = version
        self.actions_version = None

    async def get_details(self, **kwargs):
        return None

    async def get_versions(self, **kwargs):
        return [self.version]

    async def get_available_actions(self, user_id, version):
        self.actions_version = version
        return set()


class _TaskService:
    async def can_issue_task(self, **kwargs):
        return False


@pytest.mark.parametrize("is_htmx", [False, True])
def test_selectivity_scheme_form_post_saves_values_and_returns_to_tab(is_htmx):
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    service = _SchemeService()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: _Objects()
    app.dependency_overrides[get_file_service] = lambda: _Files()
    app.dependency_overrides[get_selectivity_scheme_service] = lambda: service
    app.dependency_overrides[get_rza_instruction_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_task_repository] = lambda: SimpleNamespace()
    app.dependency_overrides[get_tree_service] = lambda: _Tree()
    headers = {"HX-Request": "true"} if is_htmx else {}
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes",
            headers=headers,
            data={
                "effective_date": "2026-10-17",
                "number": "С-110-1",
                "name": "Схема ПС",
                "new_version": "false",
            },
            files={"scan_file": ("scan.pdf", b"pdf", "application/pdf")},
            follow_redirects=False,
        )
        destination = f"/objects/substation/{substation_id}?tab=selectivity-schemes"
        if is_htmx:
            assert response.status_code == 204
            assert response.headers["HX-Redirect"] == destination
        else:
            assert response.status_code == 303
            assert response.headers["location"] == destination
        assert service.create_kwargs is not None
        assert service.create_kwargs["substation_id"] == substation_id
        assert service.create_kwargs["number"] == "С-110-1"
        assert service.create_kwargs["name"] == "Схема ПС"
        assert service.create_kwargs["effective_date"] == date(2026, 10, 17)
        assert service.create_kwargs["scan_file_id"] is not None
    finally:
        app.dependency_overrides.clear()



def test_selectivity_scheme_htmx_validation_error_returns_form_fragment():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: _Objects()
    app.dependency_overrides[get_file_service] = lambda: _Files()
    app.dependency_overrides[get_selectivity_scheme_service] = (
        lambda: _SchemeService()
    )
    app.dependency_overrides[get_rza_instruction_service] = (
        lambda: SimpleNamespace()
    )
    app.dependency_overrides[get_task_repository] = (
        lambda: SimpleNamespace()
    )
    app.dependency_overrides[get_tree_service] = lambda: _Tree()

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes",
            headers={"HX-Request": "true"},
            data={
                "effective_date": "",
                "number": "С-110-1",
                "name": "Схема ПС",
                "new_version": "false",
            },
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert "Укажите дату вступления." in response.text
        assert 'id="substation-tab-content"' not in response.text
        assert 'name="effective_date"' in response.text
    finally:
        app.dependency_overrides.clear()



def test_substation_instruction_tab_renders_version_details_without_dto_attribute_error():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    version = SimpleNamespace(
        id=uuid7(), version_number=2, effective_date=date(2026, 10, 17),
        change_description="Уточнена схема", change_justification="Обновление",
        created_by_full_name="Инженер", scan_file_id=None, scan_file_name=None,
        editable_file_id=None, editable_file_name=None,
    )
    service = _InstructionService(version)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: _Objects()
    app.dependency_overrides[get_rza_instruction_service] = lambda: service
    app.dependency_overrides[get_task_service] = lambda: _TaskService()
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/instructions"
        )
        assert response.status_code == 200
        assert "Версия 2" in response.text
        assert "Уточнена схема" in response.text
        assert service.actions_version is version
    finally:
        app.dependency_overrides.clear()



def test_selectivity_scheme_unexpected_error_discards_uploaded_file():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    files = _Files()
    service = _SchemeService(error=RuntimeError("database failure"))

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: _Objects()
    app.dependency_overrides[get_file_service] = lambda: files
    app.dependency_overrides[get_selectivity_scheme_service] = lambda: service
    app.dependency_overrides[get_rza_instruction_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_task_repository] = lambda: SimpleNamespace()
    app.dependency_overrides[get_tree_service] = lambda: _Tree()

    try:
        with pytest.raises(RuntimeError, match="database failure"):
            TestClient(app).post(
                f"/objects/substation/{substation_id}/selectivity-schemes",
                headers={"HX-Request": "true"},
                data={
                    "effective_date": "2026-10-17",
                    "number": "С-110-1",
                    "name": "Схема ПС",
                    "new_version": "false",
                },
                files={"scan_file": ("scan.pdf", b"pdf", "application/pdf")},
            )

        assert len(files.discarded) == 1
        assert files.archived == []
    finally:
        app.dependency_overrides.clear()


def test_substation_scheme_transition_htmx_redirects_to_tab():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    version_id = uuid7()
    service = _TransitionService()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_selectivity_scheme_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes/"
            f"versions/{version_id}/submit",
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )

        assert response.status_code == 204
        assert response.headers["HX-Redirect"] == (
            f"/objects/substation/{substation_id}?tab=selectivity-schemes"
        )
        assert service.calls == [("submit", (user.id, substation_id, version_id))]
    finally:
        app.dependency_overrides.clear()


def test_substation_scheme_transition_returns_403_on_permission_error():
    user = SimpleNamespace(id=uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    version_id = uuid7()
    service = _TransitionService(
        error=PermissionError("Согласование запрещено.")
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_selectivity_scheme_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes/"
            f"versions/{version_id}/approve",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Согласование запрещено."
    finally:
        app.dependency_overrides.clear()


def test_substation_scheme_transition_returns_404_for_unknown_action():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    version_id = uuid7()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_selectivity_scheme_service] = (
        lambda: _TransitionService()
    )

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes/"
            f"versions/{version_id}/unknown",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Действие не найдено."
    finally:
        app.dependency_overrides.clear()


def test_substation_instruction_transition_htmx_redirects_to_tab():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id = uuid7()
    version_id = uuid7()
    service = object.__new__(RZAInstructionService)
    transition = _TransitionService()
    service.submit_for_review = transition.submit_for_review
    service.review = transition.review

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_rza_instruction_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/instructions/"
            f"versions/{version_id}/submit",
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )

        assert response.status_code == 204
        assert response.headers["HX-Redirect"] == (
            f"/objects/substation/{substation_id}?tab=instructions"
        )
        assert transition.calls == [
            ("submit", (user.id, substation_id, version_id))
        ]
    finally:
        app.dependency_overrides.clear()


def test_substation_instruction_transition_returns_403_on_permission_error():
    user = SimpleNamespace(id=uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    version_id = uuid7()
    service = _TransitionService(
        error=PermissionError("Согласование запрещено.")
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_rza_instruction_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/instructions/"
            f"versions/{version_id}/approve",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Согласование запрещено."
    finally:
        app.dependency_overrides.clear()
