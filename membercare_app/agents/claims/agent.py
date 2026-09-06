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


def get_authenticated_claim(
    claim_id: str,
    tool_context: ToolContext,
) -> dict:
    """
    Retrieve a claim through the governed Tool Gateway.

    Trusted identity comes from RequestContext locally or from
    trusted Agent Runtime session state when running remotely.
    """

    ensure_request_context_from_tool_context(
        tool_context
    )

    result = execute_tool(
        agent_name="claims_agent",
        tool_name="get_claim_by_id",
        arguments={
            "claim_id": claim_id,
        },
    )

    if isinstance(result, dict):
        returned_claim_id = result.get("claim_id")

        if returned_claim_id:
            tool_context.state[
                "current_claim_id"
            ] = returned_claim_id

    return result


claims_agent = Agent(
    name="claims_agent",
    model=MODEL_NAME,
    description=(
        "Handles healthcare claim questions such as claim status, "
        "billed amount, allowed amount, plan payment, and member "
        "responsibility."
    ),
    instruction="""
You are the MemberCareAI Claims Agent.

You answer administrative healthcare claim questions.

Use get_authenticated_claim whenever the member asks about a
specific claim.

Rules:

1. Never invent claim information.

2. Claim facts must come from get_authenticated_claim.

3. Never infer member identity or claim ownership from the
   natural-language prompt.

4. Authorization is enforced deterministically by the Tool Gateway.

5. If access is denied, not permitted, or unauthorized, do not
   reveal any protected claim facts.

6. Do not provide medical diagnosis, treatment recommendations,
   medication recommendations, or clinical advice.

7. When available, clearly explain:
   - claim status
   - billed amount
   - allowed amount
   - plan payment
   - member responsibility

8. Do not bypass governed tools.

9. If information is unavailable, say so rather than guessing.

10. Keep answers clear and member-friendly.
""",
    tools=[
        get_authenticated_claim,
    ],
)