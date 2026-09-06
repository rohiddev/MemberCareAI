from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = (
    "https://membercare-api-422936875002.us-central1.run.app"
)

MEMBER_TOKEN = "dev-member-001"
REVIEWER_TOKEN = "dev-reviewer-001"
EXECUTOR_TOKEN = "dev-executor-001"


@dataclass
class TestResult:
    name: str
    passed: bool
    expected_status: int
    actual_status: int | None
    detail: str


def cloud_run_token() -> str:
    configured = os.getenv("MEMBERCARE_CLOUD_RUN_ID_TOKEN")

    if configured:
        return configured.strip()

    completed = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        check=True,
        capture_output=True,
        text=True,
    )

    token = completed.stdout.strip()

    if not token:
        raise RuntimeError("gcloud returned an empty identity token")

    return token


def request_json(
    *,
    api_url: str,
    cloud_token: str,
    app_token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {
        "X-Serverless-Authorization": f"Bearer {cloud_token}",
        "Authorization": f"Bearer {app_token}",
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{api_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=180) as response:
            raw_body = response.read().decode("utf-8")
            return response.status, _decode_json(raw_body)

    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        return exc.code, _decode_json(raw_body)

    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc


def _decode_json(raw_body: str) -> dict[str, Any]:
    if not raw_body:
        return {}

    try:
        value = json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw_body": raw_body}

    if isinstance(value, dict):
        return value

    return {"value": value}


def approval_id_from_answer(answer: str) -> str:
    match = re.search(r"approval-[a-f0-9]{24}", answer, re.IGNORECASE)

    if not match:
        raise RuntimeError(
            "The proposal response did not contain an approval ID. "
            f"Response: {answer}"
        )

    return match.group(0).lower()


def record_test(
    results: list[TestResult],
    *,
    name: str,
    expected_status: int,
    actual_status: int,
    body: dict[str, Any],
    body_check: bool = True,
) -> None:
    passed = actual_status == expected_status and body_check
    detail_value = body.get("detail") or body.get("message") or body

    results.append(
        TestResult(
            name=name,
            passed=passed,
            expected_status=expected_status,
            actual_status=actual_status,
            detail=str(detail_value),
        )
    )

    label = "PASS" if passed else "FAIL"
    print(f"{label}: {name} ({actual_status})")


def main() -> int:
    api_url = os.getenv("MEMBERCARE_API_URL", DEFAULT_API_URL)
    token = cloud_run_token()
    session_id = f"security-eval-{uuid.uuid4()}"
    results: list[TestResult] = []

    print("Creating a fresh governed proposal...")

    status, proposal = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=MEMBER_TOKEN,
        method="POST",
        path="/chat",
        payload={
            "message": (
                "Please create a prior-authorization proposal for human "
                "review. The procedure code is 73221, the provider ID is "
                "PRV-001, and the justification is: Security evaluation "
                "requested a simulated shoulder MRI proposal. Do not submit "
                "or execute it without human approval."
            ),
            "session_id": session_id,
        },
    )

    if status != 200:
        raise RuntimeError(
            f"Could not create proposal: HTTP {status}: {proposal}"
        )

    approval_id = approval_id_from_answer(str(proposal.get("answer", "")))
    print(f"Approval ID: {approval_id}")

    review_path = f"/approvals/{approval_id}/review"
    execute_path = f"/approvals/{approval_id}/execute"

    # A pending action must not execute, even with a valid executor identity.
    status, body = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=EXECUTOR_TOKEN,
        method="POST",
        path=execute_path,
    )
    record_test(
        results,
        name="pending_approval_cannot_execute",
        expected_status=409,
        actual_status=status,
        body=body,
    )

    # Members and executors cannot perform the human review action.
    for name, app_token in (
        ("member_cannot_review", MEMBER_TOKEN),
        ("executor_cannot_review", EXECUTOR_TOKEN),
    ):
        status, body = request_json(
            api_url=api_url,
            cloud_token=token,
            app_token=app_token,
            method="POST",
            path=review_path,
            payload={
                "decision": "APPROVED",
                "review_comment": "Unauthorized security evaluation attempt.",
            },
        )
        record_test(
            results,
            name=name,
            expected_status=401,
            actual_status=status,
            body=body,
        )

    # Members and reviewers cannot execute approved actions.
    for name, app_token in (
        ("member_cannot_execute", MEMBER_TOKEN),
        ("reviewer_cannot_execute", REVIEWER_TOKEN),
    ):
        status, body = request_json(
            api_url=api_url,
            cloud_token=token,
            app_token=app_token,
            method="POST",
            path=execute_path,
        )
        record_test(
            results,
            name=name,
            expected_status=401,
            actual_status=status,
            body=body,
        )

    # A reviewer makes the one allowed decision.
    status, body = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=REVIEWER_TOKEN,
        method="POST",
        path=review_path,
        payload={
            "decision": "APPROVED",
            "review_comment": "Approved by automated cloud security evaluation.",
        },
    )
    record_test(
        results,
        name="reviewer_can_approve_pending_request",
        expected_status=200,
        actual_status=status,
        body=body,
        body_check=body.get("status") == "APPROVED",
    )

    # The approval decision is immutable.
    status, body = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=REVIEWER_TOKEN,
        method="POST",
        path=review_path,
        payload={
            "decision": "REJECTED",
            "review_comment": "Attempting a forbidden second decision.",
        },
    )
    record_test(
        results,
        name="approval_cannot_be_decided_twice",
        expected_status=409,
        actual_status=status,
        body=body,
    )

    # Only the executor may execute the stored approved payload.
    status, body = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=EXECUTOR_TOKEN,
        method="POST",
        path=execute_path,
    )
    record_test(
        results,
        name="executor_can_execute_approved_request",
        expected_status=200,
        actual_status=status,
        body=body,
        body_check=(
            body.get("execution_status") == "COMPLETED"
            and body.get("executed_by") == "EXECUTOR-001"
            and body.get("submission_mode") == "SIMULATED"
            and bool(body.get("external_reference"))
        ),
    )

    # Firestore transaction and execution state prevent a replay.
    status, body = request_json(
        api_url=api_url,
        cloud_token=token,
        app_token=EXECUTOR_TOKEN,
        method="POST",
        path=execute_path,
    )
    record_test(
        results,
        name="completed_request_cannot_execute_twice",
        expected_status=409,
        actual_status=status,
        body=body,
    )

    passed = sum(result.passed for result in results)
    failed = len(results) - passed
    report = {
        "api_url": api_url,
        "approval_id": approval_id,
        "execution_mode": "SIMULATED",
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "pass_rate": passed / len(results) if results else 0.0,
        "results": [asdict(result) for result in results],
    }

    report_path = Path("reports/membercare_cloud_security_evaluation.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(json.dumps({
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "pass_rate": report["pass_rate"],
    }, indent=2))
    print(f"Report: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc