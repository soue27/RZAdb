from pathlib import Path

import pytest

from app.infrastructure.seed.import_csv import import_csv


@pytest.mark.asyncio
async def test_import_csv_imports_test_data() -> None:
    path = Path("data/rzadb_test_data.csv")

    count = await import_csv(path)

    assert count == 56

@pytest.mark.asyncio
async def test_import_csv_rejects_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        await import_csv(path)