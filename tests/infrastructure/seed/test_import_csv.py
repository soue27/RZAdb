from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.seed.csv_importer import CSVImporter
from app.infrastructure.seed.service import RZACSVSeedService

TEST_CSV = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "rza_seed_synthetic.csv"
)


@pytest.mark.asyncio
async def test_import_csv_imports_test_data(
    db_session: AsyncSession,
    system_user_id: UUID,
) -> None:
    importer = CSVImporter(TEST_CSV)
    rows = importer.read_rows()

    service = RZACSVSeedService(db_session, actor_id=system_user_id)

    count = await service.import_rows(rows)

    assert count == 56

def test_import_csv_rejects_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.csv"

    importer = CSVImporter(path)

    with pytest.raises(FileNotFoundError):
        importer.read_rows()
