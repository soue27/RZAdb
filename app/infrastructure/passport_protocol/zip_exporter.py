from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.application.passport_protocol.service import PreparedPassportProtocol


class PassportProtocolZipExporter:
    """Упаковывает четыре подготовленных документа паспорта УРЗА в ZIP-архив.
    """
    def export(self, package: PreparedPassportProtocol) -> bytes:
        """Формирует ZIP-архив паспорта из четырёх документов в установленном порядке.

        Проверяет количество документов, допустимость имён, ожидаемые префиксы
        и уникальность имён файлов.

        Args:
            package: Подготовленный комплект документов паспорта.

        Returns:
            Бинарное содержимое ZIP-архива.

        Raises:
            ValueError: Если комплект неполный, имена небезопасны или порядок неверен.
        """
        expected = ("01_ОТД.docx", "02_Уставки", "03_Схемы", "04_ТО")
        if len(package.documents) != 4:
            raise ValueError("Passport package must contain four documents")
        names = [document.filename for document in package.documents]
        if any("/" in name or "\\" in name or name in {".", ".."} for name in names):
            raise ValueError("Passport document names must be flat")
        if names[0] != expected[0] or any(
            not names[index].startswith(expected[index])
            for index in range(1, 4)
        ):
            raise ValueError("Passport documents are not in the expected order")
        if len(set(names)) != 4:
            raise ValueError("Passport document names must be unique")

        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for document in package.documents:
                archive.writestr(document.filename, document.content)
        return output.getvalue()
