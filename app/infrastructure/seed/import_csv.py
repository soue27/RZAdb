import argparse
import asyncio
from pathlib import Path

from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.seed.csv_importer import CSVImporter
from app.infrastructure.seed.service import RZACSVSeedService


async def import_csv(path: Path) -> int:
    """Импортирует CSV-файл в базу данных."""

    importer = CSVImporter(path)
    rows = importer.read_rows()

    async with async_session_factory() as session:
        try:
            service = RZACSVSeedService(session)

            count = await service.import_rows(rows)

            await session.commit()

            return count

        except Exception:
            await session.rollback()
            raise


def main() -> None:
    """Точка входа CLI."""

    parser = argparse.ArgumentParser(
        description="Импорт тестовых данных РЗА из CSV.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Путь к CSV-файлу.",
    )

    args = parser.parse_args()

    try:
        count = asyncio.run(import_csv(args.path))
    except Exception as exc:
        print(f"Ошибка импорта: {exc}")
        raise SystemExit(1) from exc

    print("Импорт завершён.")
    print(f"Обработано строк: {count}")


if __name__ == "__main__":
    main()