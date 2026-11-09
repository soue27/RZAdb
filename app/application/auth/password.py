from pwdlib import PasswordHash


class PasswordService:
    """Хеширование и проверка паролей."""

    def __init__(self) -> None:
        """Создаёт рекомендованный pwdlib-механизм хеширования паролей."""
        self._password_hash = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        """Хеширует пароль для безопасного хранения.

        Args:
            password: Пароль в открытом виде.

        Returns:
            Хеш пароля, пригодный для сохранения в базе данных.
        """
        return self._password_hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        """Проверяет пароль по ранее сохранённому хешу.

        Args:
            password: Проверяемый пароль в открытом виде.
            password_hash: Хеш, с которым сравнивается пароль.

        Returns:
            True, если пароль соответствует хешу, иначе False.
        """
        return self._password_hash.verify(password, password_hash)