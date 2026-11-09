"""Контекст запроса, распространяемый между async-вызовами."""

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Неизменяемый контекст текущего запроса: request_id и необязательный user_id.
    """
    request_id: str
    user_id: str | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "rzadb_request_context",
    default=None,
)


def get_request_context() -> RequestContext | None:
    """Возвращает контекст текущего async execution context.

    Returns:
        RequestContext или None, если контекст не установлен.
    """
    return _request_context.get()


def set_request_context(request_id: str) -> Token[RequestContext | None]:
    """Устанавливает новый контекст запроса и возвращает token для последующего сброса.

    Args:
        request_id: Идентификатор HTTP-запроса.

    Returns:
        Token ContextVar, необходимый для reset_request_context.
    """
    return _request_context.set(RequestContext(request_id=request_id))


def bind_user_id(user_id: str) -> None:
    """Добавляет идентификатор пользователя в уже установленный контекст запроса.

    Args:
        user_id: Идентификатор аутентифицированного пользователя.
    """
    context = _request_context.get()
    if context is not None:
        _request_context.set(replace(context, user_id=user_id))


def reset_request_context(token: Token[RequestContext | None]) -> None:
    """Восстанавливает предыдущее значение контекста по token.

    Args:
        token: Token, полученный при установке контекста.
    """
    _request_context.reset(token)
