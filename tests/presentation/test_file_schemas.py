from datetime import UTC, datetime

from uuid6 import uuid7

from app.domain.file import File
from app.presentation.schemas.files import FileResponse


def test_file_response_from_file() -> None:
    file_id = uuid7()

    file = File(
        id=file_id,
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=1024,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )

    response = FileResponse.model_validate(file)

    assert response.id == file_id
    assert response.original_name == "test.pdf"
    assert response.display_name == "Тестовый файл.pdf"
    assert response.extension == ".pdf"
    assert response.size == 1024
    assert response.mime_type == "application/pdf"
    assert response.uploaded_at == file.uploaded_at


def test_file_response_does_not_expose_s3_key() -> None:
    file = File(
        id=uuid7(),
        s3_key="files/2026/09/secret.pdf",
        original_name="secret.pdf",
        display_name="Секретный файл.pdf",
        extension=".pdf",
        size=512,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )

    response = FileResponse.model_validate(file)

    assert not hasattr(response, "s3_key")

from app.presentation.schemas.files import FileUploadForm


def test_file_upload_form_accepts_valid_data() -> None:
    form = FileUploadForm(
        display_name="ПС Тестовая — ТО — 2026-09-19",
        extension=".pdf",
        mime_type="application/pdf",
    )

    assert form.display_name == "ПС Тестовая — ТО — 2026-09-19"
    assert form.extension == ".pdf"
    assert form.mime_type == "application/pdf"


def test_file_upload_form_accepts_extension_without_dot() -> None:
    form = FileUploadForm(
        display_name="test",
        extension="pdf",
        mime_type="application/pdf",
    )

    assert form.extension == "pdf"