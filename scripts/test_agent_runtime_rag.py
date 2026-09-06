from __future__ import annotations

import asyncio
import uuid
from typing import Any

import vertexai


PROJECT_ID = "membercare-ai"
LOCATION = "us-central1"

AGENT_RUNTIME_RESOURCE = (
    "projects/422936875002/"
    "locations/us-central1/"
    "reasoningEngines/1170167894244327424"
)


def get_value(
    value: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Read a value from either a dictionary or SDK response object.
    """

    if isinstance(value, dict):
        return value.get(
            key,
            default,
        )

    return getattr(
        value,
        key,
        default,
    )


def get_managed_session_id(
    managed_session: Any,
) -> str:
    """
    Extract the managed Agent Runtime session ID.
    """

    session_id = get_value(
        managed_session,
        "id",
    )

    if not session_id:
        session_id = get_value(
            managed_session,
            "session_id",
        )

    if not session_id:
        name = get_value(
            managed_session,
            "name",
        )

        if name:
            session_id = (
                str(name)
                .rstrip("/")
                .split("/")[-1]
            )

    if not session_id:
        raise RuntimeError(
            "Agent Runtime did not return a managed session ID. "
            f"Response: {managed_session!r}"
        )

    return str(
        session_id
    )


def extract_text(
    event: Any,
) -> str:
    """
    Extract normal model text or an AgentTool function result.

    Agent Runtime events may contain either:

      content.parts[].text

    or:

      content.parts[].function_response.response.result
    """

    content = get_value(
        event,
        "content",
    )

    if not content:
        return ""

    parts = get_value(
        content,
        "parts",
        [],
    ) or []

    output: list[str] = []

    for part in parts:
        # -----------------------------------------------------
        # Normal model response
        # -----------------------------------------------------

        part_text = get_value(
            part,
            "text",
        )

        if part_text:
            output.append(
                str(part_text)
            )
            continue

        # -----------------------------------------------------
        # Specialist AgentTool response
        # -----------------------------------------------------

        function_response = get_value(
            part,
            "function_response",
        )

        if not function_response:
            continue

        response = get_value(
            function_response,
            "response",
        )

        if not response:
            continue

        result = get_value(
            response,
            "result",
        )

        if result:
            output.append(
                str(result)
            )

    return "\n".join(
        output
    )


async def main() -> None:
    """
    Create a trusted managed session and test Vertex RAG retrieval.
    """

    # ---------------------------------------------------------
    # Agent Platform client
    # ---------------------------------------------------------

    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
        http_options={
            "api_version": "v1beta1",
        },
    )

    remote_agent = client.agent_engines.get(
        name=AGENT_RUNTIME_RESOURCE,
    )

    # ---------------------------------------------------------
    # Trusted application identity
    # ---------------------------------------------------------

    trusted_user_id = (
        "deployment-test-user"
    )

    trusted_app_session_id = str(
        uuid.uuid4()
    )

    session_state = {
        "trusted_request_id": str(
            uuid.uuid4()
        ),
        "trusted_user_id": (
            trusted_user_id
        ),
        "trusted_user_role": (
            "member"
        ),
        "trusted_member_id": (
            "member-10001"
        ),

        # This is the MemberCareAI application session ID.
        # It is not the Google-managed session ID.
        "trusted_session_id": (
            trusted_app_session_id
        ),
    }

    # ---------------------------------------------------------
    # Create Google-managed Agent Runtime session
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "CREATING TRUSTED MANAGED SESSION"
    )
    print("=" * 70)

    managed_session = (
        await remote_agent.async_create_session(
            user_id=trusted_user_id,
            state=session_state,
        )
    )

    managed_session_id = (
        get_managed_session_id(
            managed_session
        )
    )

    print()
    print(
        "Managed session ID:",
        managed_session_id,
    )

    # ---------------------------------------------------------
    # Execute Vertex RAG test
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "VERTEX RAG TEST"
    )
    print("=" * 70)

    query = (
        "According to the general plan knowledge documents, "
        "explain what is covered for an MRI and whether "
        "prior authorization is required. "
        "Use the search_plan_knowledge tool and cite the "
        "retrieved plan document."
    )

    extracted_responses: list[str] = []

    async for event in remote_agent.async_stream_query(
        user_id=trusted_user_id,
        session_id=managed_session_id,
        message=query,
    ):
        print()
        print(event)

        event_text = extract_text(
            event
        )

        if event_text:
            extracted_responses.append(
                event_text
            )

    # ---------------------------------------------------------
    # Display final extracted response
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "FINAL RESPONSE"
    )
    print("=" * 70)

    if not extracted_responses:
        raise RuntimeError(
            "The Agent Runtime completed without returning "
            "model text or an AgentTool result."
        )

    # Prefer the last textual result emitted by the runtime.
    final_text = extracted_responses[-1]

    print()
    print(
        final_text
    )

    print()
    print("=" * 70)
    print(
        "VERTEX RAG TEST SUCCEEDED"
    )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(
        main()
    )