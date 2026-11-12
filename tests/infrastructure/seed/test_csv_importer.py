from pathlib import Path

import pytest

from app.infrastructure.seed.csv_importer import CSVImporter

TEST_CSV = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "rza_seed_synthetic.csv"
)


def test_csv_importer_reads_rows() -> None:
    importer = CSVImporter(TEST_CSV)

    rows = importer.read_rows()

    assert len(rows) == 56
    assert rows[0]["holding_full_name"] == "СИНТЕТИЧЕСКИЙ-ХОЛДИНГ-01"
    assert rows[0]["substation_dispatch_name"] == "СИНТ-ПОДСТАНЦИЯ-01"
    assert rows[0]["connection_dispatch_name"] == "СИНТ-ПРИСОЕДИНЕНИЕ-001"
    assert rows[0]["urza_dispatch_name"] == "СИНТ-УРЗА-001"


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
