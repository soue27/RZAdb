from pathlib import Path

import pytest

from app.infrastructure.seed.csv_importer import CSVImporter


def test_csv_importer_reads_rows() -> None:
    path = Path("data/rzadb_test_data.csv")

    importer = CSVImporter(path)

    rows = importer.read_rows()

    assert len(rows) == 56
    assert rows[0]["holding_full_name"] == "Россети Урал"
    assert rows[0]["urza_dispatch_name"]


def test_csv_importer_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(
        "holding_full_name,urza_dispatch_name\n"
        "Test Holding,Test URZA\n",
        encoding="utf-8",
    )

    importer = CSVImporter(path)

    with pytest.raises(ValueError, match="отсутствуют обязательные колонки"):
        importer.read_rows()
