import asyncio

import pytest

from app.presentation.responses import TemporaryFileResponse


@pytest.mark.asyncio
async def test_temporary_file_response_removes_file_when_send_is_cancelled(tmp_path):
    file_path = tmp_path / "generated.docx"
    file_path.write_bytes(b"docx")
    response = TemporaryFileResponse(file_path)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await response(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "http_version": "1.1",
                "asgi": {"spec_version": "2.4"},
            },
            receive,
            send,
        )

    assert not file_path.exists()
