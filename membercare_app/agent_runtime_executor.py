import os
from typing import Any

import vertexai

from membercare_app.context.request_context import (
    get_member_id,
    get_request_id,
    get_session_id,
    get_user_id,
    get_user_role,
)


PROJECT_ID = "membercare-ai"
RUNTIME_LOCATION = "us-central1"

AGENT_RUNTIME_RESOURCE = os.environ.get(
    "MEMBERCARE_AGENT_RUNTIME_RESOURCE",
    (
        "projects/422936875002/"
        "locations/us-central1/"
        "reasoningEngines/576818643338264576"
    ),
)


def _extract_text_from_event(
    event: dict[str, Any],
) -> str | None:
    """
    Extract textual model output from an Agent Runtime event.
    """

    content = event.get("content")

    if not isinstance(content, dict):
        return None

    parts = content.get("parts")

    if not isinstance(parts, list):
        return None

    text_parts: list[str] = []

    for part in parts:
        if not isinstance(part, dict):
            continue

        text = part.get("text")

        if text:
            text_parts.append(str(text))

    if not text_parts:
        return None

    return "\n".join(text_parts)


def _get_managed_session_id(
    session: Any,
) -> str:
    """
    Extract the Agent Runtime generated session ID.

    Depending on SDK representation, the returned session may
    behave as an object or dictionary.
    """

    session_id = getattr(
        session,
        "id",
        None,
    )

    if session_id:
        return str(session_id)

    if isinstance(session, dict):
        session_id = session.get("id")

        if session_id:
            return str(session_id)

    raise RuntimeError(
        "Agent Runtime created a session but no session ID "
        "was returned."
    )


async def execute_runtime_agent(
    message: str,
    session_id: str,
    user_id: str,
) -> str:
    """
    Execute MemberCareAI through the managed Google Agent Runtime.

    The caller's session_id remains the MemberCareAI application
    session ID.

    Agent Runtime receives a separate managed session ID generated
    by Google.

    Trusted application identity is injected into the managed
    session's state.

    Security boundary:

        Client / prompt
              |
              X  cannot establish member identity
              |
        API / authentication
              |
        RequestContext
              |
        Managed session state
              |
        Specialist wrapper
              |
        Tool Gateway
    """

    # ========================================================
    # TRUSTED APPLICATION CONTEXT
    # ========================================================

    trusted_request_id = get_request_id()
    trusted_user_id = get_user_id()
    trusted_user_role = get_user_role()
    trusted_member_id = get_member_id()
    trusted_app_session_id = get_session_id()

    if not trusted_request_id:
        raise PermissionError(
            "Trusted request_id is missing."
        )

    if not trusted_user_id:
        raise PermissionError(
            "Trusted user_id is missing."
        )

    if not trusted_user_role:
        raise PermissionError(
            "Trusted user_role is missing."
        )

    if not trusted_member_id:
        raise PermissionError(
            "Trusted member_id is missing."
        )

    if not trusted_app_session_id:
        raise PermissionError(
            "Trusted session_id is missing."
        )

    # ========================================================
    # DEFENSIVE CONSISTENCY CHECKS
    # ========================================================

    if user_id != trusted_user_id:
        raise PermissionError(
            "Runtime user_id does not match trusted RequestContext."
        )

    if session_id != trusted_app_session_id:
        raise PermissionError(
            "Runtime session_id does not match trusted RequestContext."
        )

    # ========================================================
    # AGENT PLATFORM CLIENT
    # ========================================================

    client = vertexai.Client(
        project=PROJECT_ID,
        location=RUNTIME_LOCATION,
        http_options={
            "api_version": "v1beta1",
        },
    )

    remote_agent = client.agent_engines.get(
        name=AGENT_RUNTIME_RESOURCE
    )

    # ========================================================
    # TRUSTED SESSION STATE
    # ========================================================

    session_state = {
        "trusted_request_id": trusted_request_id,
        "trusted_user_id": trusted_user_id,
        "trusted_user_role": trusted_user_role,
        "trusted_member_id": trusted_member_id,

        # Important:
        # This is our APPLICATION session ID.
        # It is not the Google managed session resource ID.
        "trusted_session_id": trusted_app_session_id,
    }

    # ========================================================
    # CREATE GOOGLE-MANAGED SESSION
    # ========================================================

    #
    # DO NOT pass our application session_id here.
    #
    # Let Agent Runtime create a valid managed session resource
    # and return its ID.
    #

    managed_session = await remote_agent.async_create_session(
        user_id=trusted_user_id,
        state=session_state,
    )

    managed_session_id = _get_managed_session_id(
        managed_session
    )

    # ========================================================
    # REMOTE EXECUTION
    # ========================================================

    final_text = ""

    async for event in remote_agent.async_stream_query(
        user_id=trusted_user_id,
        session_id=managed_session_id,
        message=message,
    ):
        text = _extract_text_from_event(
            event
        )

        if text:
            final_text = text

    # ========================================================
    # RESULT
    # ========================================================

    if not final_text:
        raise RuntimeError(
            "Agent Runtime completed without returning "
            "a textual response."
        )

    return final_text