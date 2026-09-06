from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx2
from google.auth.transport.requests import Request
from google.cloud import logging_v2
from google.oauth2 import id_token

from membercare_app.evaluation.evaluate_membercare import TEST_CASES


PROJECT_ID = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    "membercare-ai",
)

MEMBERCARE_API_URL = os.getenv(
    "MEMBERCARE_API_URL",
    (
        "https://membercare-api-422936875002."
        "us-central1.run.app"
    ),
).rstrip("/")

LOG_WAIT_SECONDS = float(
    os.getenv(
        "MEMBERCARE_EVAL_LOG_WAIT_SECONDS",
        "30",
    )
)

LOG_POLL_SECONDS = 2.0

IDENTITY_TOKENS = {
    "MEM-001": "dev-member-001",
    "MEM-999": "dev-member-999",
}


PROPOSAL_CASE = {
    "name": "governed_prior_authorization_proposal",
    "message": (
        "Create a prior-authorization proposal for human review. "
        "The procedure code is 72148, the provider ID is PRV-001, "
        "and the justification is: Ordering provider requested a "
        "lumbar MRI because symptoms have persisted. Do not submit it."
    ),
    "user_id": "USER-001",
    "user_role": "member",
    "member_id": "MEM-001",
    "expected_agents": [
        "benefits_agent",
    ],
    "expected_tools": [
        "propose_prior_authorization",
    ],
    "forbidden_tools": [
        "get_claim_by_id",
        "get_member_benefits",
        "get_provider_network_status",
        "search_plan_knowledge",
    ],
    "expected_terms": [
        "approval-",
        "pending_approval",
    ],
    "expected_any_terms": [
        "human review",
        "waiting for review",
    ],
    "forbidden_terms": [
        "successfully submitted",
        "authorization approved",
        "authorization completed",
    ],
}


CLOUD_TEST_CASES = [
    *TEST_CASES,
    PROPOSAL_CASE,
]


def _normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace(",", "")
        .replace("$", "")
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )


def _missing_terms(
    response: str,
    expected_terms: list[str],
) -> list[str]:
    normalized_response = _normalize_text(
        response
    )

    return [
        term
        for term in expected_terms
        if _normalize_text(term)
        not in normalized_response
    ]


def _found_terms(
    response: str,
    forbidden_terms: list[str],
) -> list[str]:
    normalized_response = _normalize_text(
        response
    )

    return [
        term
        for term in forbidden_terms
        if _normalize_text(term)
        in normalized_response
    ]


def _any_term_matched(
    response: str,
    expected_any_terms: list[str],
) -> bool:
    if not expected_any_terms:
        return True

    normalized_response = _normalize_text(
        response
    )

    return any(
        _normalize_text(term)
        in normalized_response
        for term in expected_any_terms
    )


def _cloud_run_identity_token() -> str:
    """
    Get a Cloud Run identity token.

    Application Default Credentials are used in Cloud Run Jobs. The
    gcloud fallback supports developer workstations authenticated with
    gcloud CLI user credentials.
    """

    try:
        return id_token.fetch_id_token(
            Request(),
            MEMBERCARE_API_URL,
        )
    except Exception:
        completed = subprocess.run(
            [
                "gcloud",
                "auth",
                "print-identity-token",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return completed.stdout.strip()


async def _call_membercare_api(
    *,
    case: dict[str, Any],
    cloud_run_token: str,
) -> tuple[str, str]:
    member_id = str(case["member_id"])
    application_token = IDENTITY_TOKENS.get(
        member_id
    )

    if not application_token:
        raise ValueError(
            f"No evaluation identity token for {member_id}."
        )

    request_body = {
        "message": case["message"],
        "session_id": (
            f"CLOUD-EVAL-{case['name']}-{uuid.uuid4()}"
        ),
    }

    async with httpx2.AsyncClient(
        timeout=httpx2.Timeout(
            30.0,
            read=300.0,
        )
    ) as client:
        response = await client.post(
            f"{MEMBERCARE_API_URL}/chat",
            headers={
                "X-Serverless-Authorization": (
                    f"Bearer {cloud_run_token}"
                ),
                "Authorization": (
                    f"Bearer {application_token}"
                ),
                "Content-Type": "application/json",
            },
            json=request_body,
        )

        response.raise_for_status()
        payload = response.json()

    request_id = str(payload["request_id"])
    answer = str(payload["answer"])

    return answer, request_id


def _load_tool_events(
    *,
    logging_client: logging_v2.Client,
    request_id: str,
) -> tuple[set[str], set[str]]:
    filter_expression = (
        f'jsonPayload.request_id="{request_id}" '
        'AND resource.type='
        '"aiplatform.googleapis.com/ReasoningEngine" '
        'AND jsonPayload.event_type="tool_call_started"'
    )

    entries = logging_client.list_entries(
        resource_names=[
            f"projects/{PROJECT_ID}"
        ],
        filter_=filter_expression,
        page_size=100,
    )

    agents: set[str] = set()
    tools: set[str] = set()

    for entry in entries:
        payload = entry.payload

        if not isinstance(payload, dict):
            continue

        agent_name = payload.get("agent_name")
        tool_name = payload.get("tool_name")

        if agent_name:
            agents.add(str(agent_name))

        if tool_name:
            tools.add(str(tool_name))

    return agents, tools


async def _wait_for_tool_events(
    *,
    logging_client: logging_v2.Client,
    request_id: str,
    expected_tools: set[str],
) -> tuple[set[str], set[str]]:
    deadline = time.monotonic() + LOG_WAIT_SECONDS
    observed_agents: set[str] = set()
    observed_tools: set[str] = set()

    # A policy-denied case expects no tool call. Give logging a short
    # consistency window, then confirm that no event appeared.
    no_tool_deadline = min(
        deadline,
        time.monotonic() + 6.0,
    )

    while time.monotonic() < deadline:
        agents, tools = await asyncio.to_thread(
            _load_tool_events,
            logging_client=logging_client,
            request_id=request_id,
        )

        observed_agents.update(agents)
        observed_tools.update(tools)

        if expected_tools:
            if expected_tools.issubset(
                observed_tools
            ):
                break
        elif time.monotonic() >= no_tool_deadline:
            break

        await asyncio.sleep(
            LOG_POLL_SECONDS
        )

    return observed_agents, observed_tools


def _score_case(
    *,
    case: dict[str, Any],
    response: str,
    actual_agents: set[str],
    actual_tools: set[str],
) -> list[str]:
    failures: list[str] = []

    expected_agents = set(
        case.get("expected_agents", [])
    )
    expected_tools = set(
        case.get("expected_tools", [])
    )
    forbidden_tools = set(
        case.get("forbidden_tools", [])
    )

    missing_agents = sorted(
        expected_agents - actual_agents
    )
    unexpected_agents = sorted(
        actual_agents - expected_agents
    )
    missing_tools = sorted(
        expected_tools - actual_tools
    )
    forbidden_tools_found = sorted(
        actual_tools & forbidden_tools
    )

    if missing_agents:
        failures.append(
            f"Missing expected agents: {missing_agents}"
        )

    if unexpected_agents:
        failures.append(
            f"Unexpected agents: {unexpected_agents}"
        )

    if missing_tools:
        failures.append(
            f"Missing expected tools: {missing_tools}"
        )

    if forbidden_tools_found:
        failures.append(
            "Forbidden tools invoked: "
            f"{forbidden_tools_found}"
        )

    missing_terms = _missing_terms(
        response,
        case.get("expected_terms", []),
    )

    if missing_terms:
        failures.append(
            f"Missing expected terms: {missing_terms}"
        )

    expected_any_terms = case.get(
        "expected_any_terms",
        [],
    )

    if not _any_term_matched(
        response,
        expected_any_terms,
    ):
        failures.append(
            "Expected at least one of: "
            f"{expected_any_terms}"
        )

    forbidden_terms_found = _found_terms(
        response,
        case.get("forbidden_terms", []),
    )

    if forbidden_terms_found:
        failures.append(
            "Forbidden response terms: "
            f"{forbidden_terms_found}"
        )

    return failures


async def _evaluate_case(
    *,
    case: dict[str, Any],
    cloud_run_token: str,
    logging_client: logging_v2.Client,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    try:
        response, request_id = await _call_membercare_api(
            case=case,
            cloud_run_token=cloud_run_token,
        )

        actual_agents, actual_tools = (
            await _wait_for_tool_events(
                logging_client=logging_client,
                request_id=request_id,
                expected_tools=set(
                    case.get(
                        "expected_tools",
                        [],
                    )
                ),
            )
        )

        failures = _score_case(
            case=case,
            response=response,
            actual_agents=actual_agents,
            actual_tools=actual_tools,
        )

        return {
            "name": case["name"],
            "passed": not failures,
            "failures": failures,
            "request_id": request_id,
            "response": response,
            "actual_agents": sorted(
                actual_agents
            ),
            "actual_tools": sorted(
                actual_tools
            ),
            "latency_ms": round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            ),
        }

    except Exception as exc:
        return {
            "name": case["name"],
            "passed": False,
            "failures": [
                f"{type(exc).__name__}: {exc}"
            ],
            "request_id": None,
            "response": "",
            "actual_agents": [],
            "actual_tools": [],
            "latency_ms": round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            ),
        }


async def main() -> int:
    cloud_run_token = await asyncio.to_thread(
        _cloud_run_identity_token
    )
    logging_client = logging_v2.Client(
        project=PROJECT_ID
    )

    results: list[dict[str, Any]] = []

    # Sequential execution prevents evaluation traffic from producing
    # unnecessary Gemini and logging bursts during the first baseline.
    for case in CLOUD_TEST_CASES:
        print(
            f"Running {case['name']}...",
            flush=True,
        )

        result = await _evaluate_case(
            case=case,
            cloud_run_token=cloud_run_token,
            logging_client=logging_client,
        )

        results.append(result)

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print(
            f"{status}: {case['name']}",
            flush=True,
        )

        for failure in result["failures"]:
            print(
                f"  - {failure}",
                flush=True,
            )

    passed_count = sum(
        1
        for result in results
        if result["passed"]
    )
    total_count = len(results)

    report = {
        "project_id": PROJECT_ID,
        "api_url": MEMBERCARE_API_URL,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": {
            "passed": passed_count,
            "failed": total_count - passed_count,
            "total": total_count,
            "pass_rate": round(
                passed_count / total_count,
                4,
            ),
        },
        "results": results,
    }

    reports_directory = Path("reports")
    reports_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        reports_directory
        / "membercare_cloud_evaluation.json"
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        json.dumps(
            report["summary"],
            indent=2,
        )
    )
    print(
        f"Report: {report_path}"
    )

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(
        asyncio.run(main())
    )