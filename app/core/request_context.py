from contextvars import ContextVar, Token
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    user_id: str | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "rzadb_request_context",
    default=None,
)


def get_request_context() -> RequestContext | None:
    return _request_context.get()


def set_request_context(request_id: str) -> Token[RequestContext | None]:
    return _request_context.set(RequestContext(request_id=request_id))


def bind_user_id(user_id: str) -> None:
    context = _request_context.get()
    if context is not None:
        _request_context.set(replace(context, user_id=user_id))


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _request_context.reset(token)
