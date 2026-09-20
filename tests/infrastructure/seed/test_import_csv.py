from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.seed.csv_importer import CSVImporter
from app.infrastructure.seed.service import RZACSVSeedService


@pytest.mark.asyncio
async def test_import_csv_imports_test_data(
    db_session: AsyncSession,
) -> None:
    path = Path("data/rzadb_test_data.csv")

    importer = CSVImporter(path)
    rows = importer.read_rows()

    service = RZACSVSeedService(db_session)

    count = await service.import_rows(rows)

    assert count == 56

def test_import_csv_rejects_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.csv"

    importer = CSVImporter(path)

    with pytest.raises(FileNotFoundError):
        importer.read_rows()