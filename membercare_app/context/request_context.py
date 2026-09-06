from contextvars import ContextVar


# ============================================================
# REQUEST CONTEXT VARIABLES
# ============================================================

_request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_user_id: ContextVar[str | None] = ContextVar(
    "user_id",
    default=None,
)

_user_role: ContextVar[str | None] = ContextVar(
    "user_role",
    default=None,
)

_member_id: ContextVar[str | None] = ContextVar(
    "member_id",
    default=None,
)

_session_id: ContextVar[str | None] = ContextVar(
    "session_id",
    default=None,
)


# ============================================================
# SET REQUEST CONTEXT
# ============================================================

def set_request_context(
    request_id: str,
    user_id: str,
    user_role: str,
    member_id: str,
    session_id: str,
) -> None:
    """
    Store trusted identity and request metadata for the
    current request.

    In production, these values should come from authenticated
    identity information, not directly from the user's prompt.
    """

    _request_id.set(request_id)
    _user_id.set(user_id)
    _user_role.set(user_role)
    _member_id.set(member_id)
    _session_id.set(session_id)


# ============================================================
# GETTERS
# ============================================================

def get_request_id() -> str | None:
    return _request_id.get()


def get_user_id() -> str | None:
    return _user_id.get()


def get_user_role() -> str | None:
    return _user_role.get()


def get_member_id() -> str | None:
    return _member_id.get()


def get_session_id() -> str | None:
    return _session_id.get()