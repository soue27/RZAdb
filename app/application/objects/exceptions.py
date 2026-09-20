class ObjectNotFoundError(Exception):
    """Запрошенный объект не существует."""


class ObjectAccessDeniedError(Exception):
    """Пользователь не имеет доступа к объекту."""