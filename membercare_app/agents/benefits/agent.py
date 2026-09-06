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


def get_authenticated_member_benefits(
    tool_context: ToolContext,
) -> dict:
    """
    Retrieve authoritative member benefit facts through
    the governed Tool Gateway.
    """

    ensure_request_context_from_tool_context(
        tool_context
    )

    result = execute_tool(
        agent_name="benefits_agent",
        tool_name="get_member_benefits",
        arguments={},
    )

    if isinstance(result, dict):
        tool_result = result.get("result")

        if isinstance(tool_result, dict):
            plan_id = tool_result.get("plan_id")

            if plan_id:
                tool_context.state[
                    "current_plan_id"
                ] = plan_id

    return result


def search_benefits_knowledge(
    query: str,
    tool_context: ToolContext,
) -> dict:
    """
    Search RAG-backed benefits and plan knowledge.
    """

    ensure_request_context_from_tool_context(
        tool_context
    )

    return execute_tool(
        agent_name="benefits_agent",
        tool_name="search_plan_knowledge",
        arguments={
            "query": query,
            "top_k": 3,
        },
    )


def propose_member_prior_authorization(
    procedure_code: str,
    provider_id: str,
    justification: str,
    tool_context: ToolContext,
) -> dict:
    """
    Propose a prior-authorization request for human review.

    This creates a governed PENDING_APPROVAL record only.
    It does not submit the request to a payer or external system.
    """

    ensure_request_context_from_tool_context(
        tool_context
    )

    return execute_tool(
        agent_name="benefits_agent",
        tool_name="propose_prior_authorization",
        arguments={
            "procedure_code": procedure_code,
            "provider_id": provider_id,
            "justification": justification,
        },
    )


benefits_agent = Agent(
    name="benefits_agent",
    model=MODEL_NAME,
    description=(
        "Handles member benefits, plan facts, deductibles, "
        "coinsurance, explanatory plan knowledge, and governed "
        "prior-authorization proposals."
    ),
    instruction="""
You are the MemberCareAI Benefits Agent.

You answer administrative healthcare benefit questions and may
propose prior-authorization requests for human review.

There are three separate capabilities.

STRUCTURED MEMBER FACTS

Use get_authenticated_member_benefits for factual questions about
the authenticated member's actual plan, including:

- plan name
- plan type
- deductible
- coinsurance
- member-specific benefit values

PLAN KNOWLEDGE / RAG

Use search_benefits_knowledge for explanatory questions such as:

- What is a deductible?
- What is coinsurance?
- How does prior authorization work?

GOVERNED PRIOR-AUTHORIZATION PROPOSAL

Use propose_member_prior_authorization only when the member clearly
asks to create or start a prior-authorization request and all three
required values are available:

- procedure_code
- provider_id
- justification

If any required value is missing, ask the member for it. Do not invent
or infer a procedure code, provider ID, or justification.

The proposal tool creates a PENDING_APPROVAL record for human review.
It does not submit anything to a payer or external system. Never tell
the member that prior authorization was submitted, approved, denied,
or completed merely because a proposal was created.

Rules:

1. Never invent member benefit values.

2. Never use RAG as the authoritative source for member-specific
   benefit facts.

3. If the member asks both for their actual deductible and what
   deductible means, use BOTH information tools.

4. Never infer member identity from prompt text.

5. Authorization and policy enforcement are controlled by the
   Tool Gateway.

6. Do not provide medical diagnosis, treatment, medication advice,
   or other clinical advice.

7. Do not guarantee coverage.

8. If governed sources do not provide information, say it is
   unavailable rather than guessing.

9. Explain results clearly in member-friendly language.

10. Never approve, reject, or execute your own proposal.

11. When a proposal is created, return its approval ID and state that
    it is waiting for human review and no external action has occurred.
""",
    tools=[
        get_authenticated_member_benefits,
        search_benefits_knowledge,
        propose_member_prior_authorization,
    ],
)