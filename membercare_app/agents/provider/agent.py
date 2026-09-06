from google.adk.agents import Agent
from google.adk.tools import ToolContext

from membercare_app.config.model import (
    MODEL_NAME,
    configure_model_environment,
)
from membercare_app.context.runtime_context import (
    ensure_request_context_from_tool_context,
)
from membercare_app.tool_gateway.gateway import execute_tool


configure_model_environment()


def get_authenticated_provider_network_status(
    provider_id: str,
    tool_context: ToolContext,
) -> dict:
    """
    Retrieve provider network information through
    the governed Tool Gateway.
    """

    ensure_request_context_from_tool_context(
        tool_context
    )

    result = execute_tool(
        agent_name="provider_agent",
        tool_name="get_provider_network_status",
        arguments={
            "provider_id": provider_id,
        },
    )

    if isinstance(result, dict):
        returned_provider_id = result.get(
            "provider_id"
        )

        if returned_provider_id:
            tool_context.state[
                "current_provider_id"
            ] = returned_provider_id

    return result


provider_agent = Agent(
    name="provider_agent",
    model=MODEL_NAME,
    description=(
        "Handles provider-network questions including provider "
        "identity, specialty, active status, and network status."
    ),
    instruction="""
You are the MemberCareAI Provider Network Agent.

You answer administrative healthcare provider-network questions.

Use get_authenticated_provider_network_status whenever the member
asks about a specific provider.

Rules:

1. Provider facts must come from the governed provider tool.

2. Never invent provider information.

3. Never infer trusted member identity from the natural-language
   prompt.

4. Authorization and policy are enforced by the Tool Gateway.

5. Clearly explain whether the provider is:
   - in network
   - out of network
   - inactive
   - unavailable

6. Network participation does not guarantee coverage for a
   particular healthcare service.

7. Coverage and member cost can depend on:
   - member plan
   - service
   - prior authorization
   - other plan requirements

8. Do not provide diagnosis, treatment recommendations,
   medication advice, or clinical advice.

9. If information cannot be retrieved, say so rather than guessing.

10. Keep responses clear and member-friendly.
""",
    tools=[
        get_authenticated_provider_network_status,
    ],
)