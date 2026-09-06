import threading


# ============================================================
# THREAD-SAFE TOOL EXECUTION TRACKER
# ============================================================
#
# Structure:
#
# {
#     "request-id-1": {
#         "get_member_benefits",
#         "search_plan_knowledge",
#     },
#
#     "request-id-2": {
#         "get_claim_by_id",
#     },
# }
#
# request_id is used as the correlation key because ADK may
# execute agents and tools across different async contexts.
# ============================================================


_lock = threading.Lock()


_invoked_tools_by_request: dict[
    str,
    set[str],
] = {}


# ============================================================
# RECORD TOOL
# ============================================================

def record_tool(
    request_id: str,
    tool_name: str,
) -> None:
    """
    Record that a governed tool was actually invoked
    for a particular MemberCareAI request.

    This is used by the evaluation framework to verify
    tool-selection behavior.

    Example:

        Question:
            "What does deductible mean?"

        Expected:
            search_plan_knowledge

        Unexpected:
            get_member_benefits

    The tracker is keyed by request_id so concurrent
    requests remain isolated.
    """

    if not request_id:
        return

    if not tool_name:
        return

    with _lock:

        invoked_tools = (
            _invoked_tools_by_request.setdefault(
                request_id,
                set(),
            )
        )

        invoked_tools.add(
            tool_name
        )


# ============================================================
# GET INVOKED TOOLS
# ============================================================

def get_invoked_tools(
    request_id: str,
) -> set[str]:
    """
    Return the set of governed tools invoked for one
    MemberCareAI request.

    A defensive copy is returned so callers cannot mutate
    the internal tracker.
    """

    if not request_id:
        return set()

    with _lock:

        return set(
            _invoked_tools_by_request.get(
                request_id,
                set(),
            )
        )


# ============================================================
# CLEAR REQUEST
# ============================================================

def clear_request_tools(
    request_id: str,
) -> None:
    """
    Remove tool-routing evidence after an evaluation case
    has completed.

    This prevents the in-memory evaluation tracker from
    growing indefinitely during repeated local evaluation
    runs.
    """

    if not request_id:
        return

    with _lock:

        _invoked_tools_by_request.pop(
            request_id,
            None,
        )