MemberCareAI

MemberCareAI is a governed, multi-agent healthcare member-support platform built on Google Cloud. 
It answers administrative questions about claims, benefits, provider networks, 
and plan terminology while enforcing trusted identity, tool authorization, member-data isolation, 
human approval, and auditable execution outside the language model.

Portfolio status: deployed and evaluated on GCP. 
Functional/governance evaluation: 10/10. Cloud security evaluation: 9/9. Combined result: 19/19 (100%).

Why this project exists

Healthcare assistants must do more than generate fluent answers. T
hey must retrieve authoritative information, prevent cross-member data access,
avoid clinical advice, separate read operations from state-changing actions,
and produce evidence showing what the system actually did.

MemberCareAI demonstrates those controls in a production-style architecture:

A supervisor routes requests to specialized agents.

Agents can select only explicitly registered tools.

A deterministic Tool Gateway enforces authorization and reliability controls.

Member-specific facts come from Firestore, while explanatory plan knowledge comes from Vertex AI RAG.

State-changing prior-authorization proposals require a separate human reviewer.

Approved actions execute through a private MCP service using a separate executor identity.

Logs correlate Cloud Run requests, managed-agent activity, agent routing, and tool calls.

Architecture

flowchart TD
    U["Authenticated member"] --> API["Cloud Run API"]
    API --> O["Outer orchestrator"]
    O --> AR["Vertex AI Agent Runtime"]
    AR --> S["Supervisor agent"]
    S --> A["Specialist agents"]
    A --> G["Tool Gateway"]
    G --> F["Firestore facts"]
    G --> R["Vertex AI RAG"]
    G --> P["Pending approval"]
    P --> H["Human reviewer"]
    H --> E["Governed executor"]
    E --> M["Private MCP service"]

Deployed request paths

Read-only member inquiry:

Cloud Run API
  → trusted request context
  → managed Agent Runtime
  → supervisor
  → specialist agent
  → Tool Gateway
  → Firestore and/or Vertex AI RAG
  → grounded member response

Governed state-changing action:

Member proposal
  → PENDING_APPROVAL in Firestore
  → separate reviewer identity
  → APPROVED
  → separate executor identity
  → private Cloud Run MCP service
  → simulated external reference
  → COMPLETED

Core components

Component

Responsibility

Cloud Run API

Authenticated /chat, approval-review, and execution endpoints

Outer orchestrator

Request lifecycle, policy checks, context, memory, persistence, and tracing

Managed Agent Runtime

Hosts the deployable ADK agent application

Supervisor agent

Selects the minimum required specialist agents and synthesizes results

Claims agent

Retrieves authorized claim facts

Benefits agent

Retrieves member benefits, searches plan knowledge, and creates governed proposals

Provider agent

Retrieves provider-network facts

Tool Gateway

Tool registration, agent permissions, trusted context, retries, timeouts, circuit breakers, and events

Firestore

Member facts, claims, sessions, providers, and approval-state records

Vertex AI RAG

Explanatory plan-document retrieval

Approval reviewer

Performs the one allowed PENDING_APPROVAL → APPROVED/REJECTED transition

Approval executor

Loads the stored approved payload; callers cannot replace approved action fields

MCP service

Exposes the controlled prior-authorization submission capability over Streamable HTTP

Governance boundaries

Trusted identity

The request body never supplies member_id. The API resolves identity server-side and establishes trusted request context containing:

request_id

session_id

user_id

user_role

member_id

Agents and tools consume this trusted context. Prompt text cannot change the authenticated member.

Deterministic Tool Gateway

The LLM may decide which available capability is useful, but it does not control authorization. The gateway independently verifies:

Trusted request context exists.

The tool is registered.

The calling agent is allowed to use it.

Arguments satisfy the capability contract.

Reliability controls permit execution.

Start, completion, denial, and failure events are emitted.

Human approval state machine

stateDiagram-v2
    [*] --> PENDING_APPROVAL: Proposal created
    PENDING_APPROVAL --> APPROVED: Reviewer approves
    PENDING_APPROVAL --> REJECTED: Reviewer rejects
    APPROVED --> EXECUTING: Executor starts
    EXECUTING --> COMPLETED: MCP succeeds
    EXECUTING --> EXECUTION_FAILED: MCP fails

The agent may create a proposal but cannot approve or execute it. The reviewer cannot execute it, and the executor cannot review it. Firestore transactions protect state transitions and prevent repeated decisions or executions.

Clinical-safety boundary

MemberCareAI handles administrative healthcare questions. 
A deterministic request-level policy blocks diagnosis, medication, dosage,
treatment recommendations, and medical decision-making before the agent runtime is invoked.

Tool inventory

Tool

Agent

Data source

Action type

get_claim_by_id

Claims

Firestore

Sensitive read

get_member_benefits

Benefits

Firestore

Sensitive read

search_plan_knowledge

Benefits

Vertex AI RAG

Read

get_provider_network_status

Provider

Firestore

Read

propose_prior_authorization

Benefits

Firestore

Creates approval record only

submit_prior_authorization

Executor only

Private MCP service

Simulated governed action

The final MCP execution tool is not registered as an agent tool. 
Only the deterministic approval executor can call it after loading an approved Firestore record.

Reliability and observability

The gateway includes:

Per-tool authorization

Timeouts

Bounded retries

Per-tool circuit breakers

Idempotent proposal identifiers

Transactional approval transitions

Replay prevention

Structured events and traces

The same request_id correlates the outer Cloud Run request with managed Agent Runtime events, agent names, tool names, gateway status, circuit state, and latency.

Evaluation evidence

Functional and governance evaluation — 10/10

Scenario

Result

Claim status and member cost

PASS

Member benefits

PASS

Provider-network status

PASS

Unauthorized claim access

PASS

Three-domain request

PASS

Clinical-advice guardrail

PASS

RAG deductible definition

PASS

Member-specific deductible fact

PASS

Combined RAG and member fact

PASS

Governed prior-authorization proposal

PASS

Cloud security evaluation — 9/9

Control

Result

Pending approval cannot execute

PASS

Member cannot review

PASS

Executor cannot review

PASS

Member cannot execute

PASS

Reviewer cannot execute

PASS

Reviewer can approve a pending request

PASS

Approval cannot be decided twice

PASS

Executor can execute an approved request

PASS

Completed request cannot execute twice

PASS

Reports are written to:

reports/membercare_cloud_evaluation.json
reports/membercare_cloud_security_evaluation.json

Run the cloud evaluations

Functional and governance suite:

GOOGLE_CLOUD_PROJECT='membercare-ai' \
MEMBERCARE_API_URL='https://membercare-api-422936875002.us-central1.run.app' \
uv run python -m membercare_app.evaluation.evaluate_cloud

Security suite:

GOOGLE_CLOUD_PROJECT='membercare-ai' \
MEMBERCARE_API_URL='https://membercare-api-422936875002.us-central1.run.app' \
uv run python -m membercare_app.evaluation.evaluate_security

Both suites exercise the deployed GCP architecture. The action evaluator uses submission_mode: SIMULATED and does not submit data to a real payer.

Demonstration flow

Send a member question involving benefits, claims, provider status, or plan terminology.

Show the grounded response and returned request_id.

Use Cloud Logging to show the supervisor route and tool calls correlated by that ID.

Ask the benefits agent to create a prior-authorization proposal.

Show the Firestore record in PENDING_APPROVAL with NOT_EXECUTED.

Demonstrate that an executor cannot run the pending proposal.

Approve it using the separate reviewer identity.

Execute it using the separate executor identity.

Show the private MCP request, simulated external reference, and COMPLETED state.

Attempt a second decision and execution; show both return 409 Conflict.

Current GCP deployment

Resource

Value

Project

membercare-ai

Region

us-central1

API service

membercare-api

API URL

https://membercare-api-422936875002.us-central1.run.app

Managed runtime

projects/422936875002/locations/us-central1/reasoningEngines/6297938282470703104

MCP service

membercare-prior-auth-mcp

MCP access

Private Cloud Run service

MCP transport

Streamable HTTP at /mcp

Technology stack

Python 3.13

FastAPI and Uvicorn

Google ADK

Gemini

Vertex AI Agent Runtime

Vertex AI RAG Engine

Google Cloud Run

Google Cloud Firestore

Model Context Protocol (MCP) 2.x

OpenTelemetry and Google Cloud Logging

uv for dependency and environment management

Repository structure

membercare_app/
├── agents/                 # Supervisor and specialist agents
├── context/                # Trusted request/runtime context
├── evaluation/             # Functional and security cloud evaluations
├── memory/                 # Durable conversation memory
├── observability/          # Events and tracing
├── policy/                 # Deterministic request policies
├── reliability/            # Retry, timeout, and circuit breaker
├── security/               # Member, reviewer, and executor identities
├── tool_gateway/           # Governed capability boundary
├── tools/                  # Claims, benefits, provider, RAG, proposals
├── approval_executor.py
├── approval_review.py
├── api.py
└── orchestrator.py

membercare_mcp/
└── prior_authorization_server.py

scripts/
├── create_vertex_rag.py
├── deploy_agent_runtime.py
├── index_knowledge.py
└── seed_firestore.py

Production-hardening roadmap

This project intentionally distinguishes a validated portfolio deployment from a production 
healthcare implementation.

Before production use:

Replace development bearer tokens with validated enterprise OAuth/OIDC JWT claims.

Store identity configuration and secrets in Secret Manager.

Replace the simulated payer operation with a contracted, secured external integration.

Add encryption and retention policies aligned with organizational compliance requirements.

Add reviewer queues, notification, expiration, cancellation, and recovery workflows.

Add continuous evaluation in CI/CD with release thresholds.

Add adversarial prompt, data-leakage, load, chaos, and dependency-failure tests.

Complete formal threat modeling, privacy review, and healthcare compliance assessment.

Key design decisions

LLMs propose; deterministic systems authorize. The model can select an available tool, 
but code enforces identity, permissions, state, and execution.

Member facts and plan explanations remain separate. Firestore is authoritative for member-specific data; 
RAG explains plan documents.

Approval is not execution. Proposal, review, and execution are separate capabilities owned by separate identities.

The approved payload is immutable at execution time. The executor accepts only an approval ID 
and loads the stored action itself.

Evidence is part of the architecture. Evaluation reports and correlated events demonstrate behavior instead of relying on architectural claims alone.

Interview summary

I built and deployed MemberCareAI, a governed multi-agent healthcare assistant on Google Cloud. 
A supervisor routes member questions to 
claims, benefits, and provider specialists running on Vertex AI Agent Runtime. 
All capabilities pass through a deterministic Tool Gateway that enforces trusted identity, 
agent permissions, retries, timeouts, circuit breakers, and audit events. 
Member facts come from Firestore, explanatory plan content comes from Vertex AI RAG, 
and sensitive prior-authorization actions use human approval with separate reviewer 
and executor identities. Approved actions execute through a private MCP service on Cloud Run. 
The deployed platform passed 19 functional, governance, and security evaluations with a 100% pass rate.

Disclaimer

This is a portfolio and engineering demonstration. It uses development application identities and a simulated prior-authorization submission. It is not a production clinical system, does not provide medical advice, and does not submit requests to a real payer.