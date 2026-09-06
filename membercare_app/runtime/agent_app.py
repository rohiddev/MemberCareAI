from __future__ import annotations

from vertexai.agent_engines import AdkApp

from membercare_app.agents.supervisor.agent import root_agent


APP_NAME = "membercareai"


# ---------------------------------------------------------------------
# Managed ADK application
# ---------------------------------------------------------------------
#
# root_agent is the MemberCareAI supervisor.
#
# The supervisor owns:
#   - intent/routing decisions
#   - delegation to specialist agents
#   - synthesis of specialist results
#
# Specialist agents currently include:
#   - claims_agent
#   - benefits_agent
#   - provider_agent
#
# The deterministic control plane remains outside the LLM:
#   - RequestContext
#   - Tool Gateway
#   - authorization
#   - policy
#   - reliability
#   - approvals / HITL
#   - audit
#
# AdkApp is the deployable wrapper expected by Vertex AI
# Agent Runtime / Reasoning Engine.
# ---------------------------------------------------------------------

agent_app = AdkApp(
    agent=root_agent,
    app_name=APP_NAME,
    enable_tracing=True,
)