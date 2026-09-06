import threading


_lock = threading.Lock()

_invoked_agents_by_request: dict[
    str,
    set[str],
] = {}


def record_agent(
    request_id: str,
    agent_name: str,
) -> None:
    """
    Record that an authorized specialist actually reached
    the Tool Gateway during this request.
    """

    if not request_id:
        return

    with _lock:
        agents = _invoked_agents_by_request.setdefault(
            request_id,
            set(),
        )

        agents.add(
            agent_name
        )


def get_invoked_agents(
    request_id: str,
) -> set[str]:
    """
    Return the specialist agents that actually executed
    authorized tools for the supplied request.
    """

    with _lock:
        return set(
            _invoked_agents_by_request.get(
                request_id,
                set(),
            )
        )


def clear_request(
    request_id: str,
) -> None:
    """
    Remove routing evidence after the evaluation case
    has completed.
    """

    with _lock:
        _invoked_agents_by_request.pop(
            request_id,
            None,
        )