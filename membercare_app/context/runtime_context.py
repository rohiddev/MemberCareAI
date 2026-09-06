from google.adk.tools import ToolContext

from membercare_app.context.request_context import (
    get_member_id,
    get_request_id,
    get_session_id,
    get_user_id,
    get_user_role,
    set_request_context,
)


def ensure_request_context_from_tool_context(
    tool_context: ToolContext,
) -> None:
    """
    Restore MemberCareAI trusted RequestContext from the
    managed ADK session state.

    Local execution:
        The outer orchestrator already establishes RequestContext.

    Managed Agent Runtime:
        Trusted identity arrives through ADK session state and
        must be restored before the Tool Gateway executes.

    Security:
        Identity is never taken from the natural-language prompt.
        Missing or inconsistent identity fails closed.
    """

    # ========================================================
    # 1. CHECK FOR AN EXISTING TRUSTED CONTEXT
    # ========================================================

    existing_request_id = get_request_id()
    existing_user_id = get_user_id()
    existing_user_role = get_user_role()
    existing_member_id = get_member_id()
    existing_session_id = get_session_id()

    # If all required values already exist, local orchestration
    # has already established the trusted context.

    if all(
        [
            existing_request_id,
            existing_user_id,
            existing_user_role,
            existing_member_id,
            existing_session_id,
        ]
    ):
        return

    # ========================================================
    # 2. READ TRUSTED ADK SESSION STATE
    # ========================================================

    state = tool_context.state

    if state is None:
        raise PermissionError(
            "Managed Agent Runtime session state is unavailable."
        )

    trusted_request_id = state.get(
        "trusted_request_id"
    )

    trusted_user_id = state.get(
        "trusted_user_id"
    )

    trusted_user_role = state.get(
        "trusted_user_role"
    )

    trusted_member_id = state.get(
        "trusted_member_id"
    )

    trusted_session_id = state.get(
        "trusted_session_id"
    )

    # ========================================================
    # 3. FAIL CLOSED IF TRUSTED IDENTITY IS INCOMPLETE
    # ========================================================

    required_values = {
        "trusted_request_id": trusted_request_id,
        "trusted_user_id": trusted_user_id,
        "trusted_user_role": trusted_user_role,
        "trusted_member_id": trusted_member_id,
        "trusted_session_id": trusted_session_id,
    }

    missing = [
        key
        for key, value in required_values.items()
        if not value
    ]

    if missing:
        raise PermissionError(
            "Trusted Agent Runtime identity is incomplete. "
            f"Missing fields: {', '.join(missing)}"
        )

    # ========================================================
    # 4. RESTORE MEMBERCARE REQUEST CONTEXT
    # ========================================================

    set_request_context(
        request_id=str(trusted_request_id),
        user_id=str(trusted_user_id),
        user_role=str(trusted_user_role),
        member_id=str(trusted_member_id),
        session_id=str(trusted_session_id),
    )

    # ========================================================
    # 5. VERIFY RESTORATION
    # ========================================================

    restored_request_id = get_request_id()
    restored_user_id = get_user_id()
    restored_user_role = get_user_role()
    restored_member_id = get_member_id()
    restored_session_id = get_session_id()

    if restored_request_id != str(
        trusted_request_id
    ):
        raise RuntimeError(
            "Failed to restore trusted request_id."
        )

    if restored_user_id != str(
        trusted_user_id
    ):
        raise RuntimeError(
            "Failed to restore trusted user_id."
        )

    if restored_user_role != str(
        trusted_user_role
    ):
        raise RuntimeError(
            "Failed to restore trusted user_role."
        )

    if restored_member_id != str(
        trusted_member_id
    ):
        raise RuntimeError(
            "Failed to restore trusted member_id."
        )

    if restored_session_id != str(
        trusted_session_id
    ):
        raise RuntimeError(
            "Failed to restore trusted session_id."
        )