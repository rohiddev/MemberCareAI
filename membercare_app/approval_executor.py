from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx2
from google.auth.transport.requests import Request
from google.cloud import firestore
from google.oauth2 import id_token
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from membercare_app.config.firestore import get_firestore_client
from membercare_mcp.prior_authorization_server import (
    mcp as local_prior_authorization_mcp,
)


APPROVAL_COLLECTION = "approval_requests"

APPROVED = "APPROVED"

NOT_EXECUTED = "NOT_EXECUTED"
EXECUTING = "EXECUTING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

MCP_URL_ENVIRONMENT_VARIABLE = (
    "MEMBERCARE_PRIOR_AUTHORIZATION_MCP_URL"
)

MCP_AUDIENCE_ENVIRONMENT_VARIABLE = (
    "MEMBERCARE_PRIOR_AUTHORIZATION_MCP_AUDIENCE"
)


class ApprovalExecutionError(Exception):
    """Base error for governed approval execution failures."""


class ApprovalExecutionNotFoundError(ApprovalExecutionError):
    """Raised when the approval record does not exist."""


class ApprovalExecutionStateConflictError(ApprovalExecutionError):
    """Raised when the approval is not eligible for execution."""


def _claim_approved_execution(
    *,
    approval_id: str,
    executor_id: str,
) -> dict[str, Any]:
    """Atomically claim one approved, unexecuted action."""

    db = get_firestore_client()
    document = (
        db.collection(APPROVAL_COLLECTION)
        .document(approval_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def claim(
        active_transaction,
    ) -> dict[str, Any]:
        snapshot = document.get(
            transaction=active_transaction
        )

        if not snapshot.exists:
            raise ApprovalExecutionNotFoundError(
                f"Approval request '{approval_id}' was not found."
            )

        record = snapshot.to_dict() or {}
        approval_status = record.get("status")
        execution_status = record.get(
            "execution_status"
        )

        if approval_status != APPROVED:
            raise ApprovalExecutionStateConflictError(
                "Approval request is not approved. "
                f"Current status: {approval_status}."
            )

        if execution_status != NOT_EXECUTED:
            raise ApprovalExecutionStateConflictError(
                "Approval request is not eligible for execution. "
                f"Current execution status: {execution_status}."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        updates = {
            "execution_status": EXECUTING,
            "execution_started_at": now,
            "execution_updated_at": now,
            "executed_by": executor_id,
            "execution_error": None,
        }

        active_transaction.update(
            document,
            updates,
        )

        return {
            **record,
            **updates,
        }

    return claim(transaction)


def _mark_execution_completed(
    *,
    approval_id: str,
    executor_id: str,
    mcp_result: dict[str, Any],
) -> None:
    """Atomically record successful MCP execution."""

    db = get_firestore_client()
    document = (
        db.collection(APPROVAL_COLLECTION)
        .document(approval_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def complete(
        active_transaction,
    ) -> None:
        snapshot = document.get(
            transaction=active_transaction
        )

        if not snapshot.exists:
            raise ApprovalExecutionNotFoundError(
                f"Approval request '{approval_id}' was not found."
            )

        record = snapshot.to_dict() or {}

        if record.get("execution_status") != EXECUTING:
            raise ApprovalExecutionStateConflictError(
                "Execution is no longer in the EXECUTING state."
            )

        if record.get("executed_by") != executor_id:
            raise ApprovalExecutionStateConflictError(
                "Execution is owned by a different executor."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        active_transaction.update(
            document,
            {
                "execution_status": COMPLETED,
                "execution_updated_at": now,
                "executed_at": now,
                "external_reference": mcp_result.get(
                    "external_reference"
                ),
                "external_submission_status": mcp_result.get(
                    "submission_status"
                ),
                "submission_mode": mcp_result.get(
                    "submission_mode"
                ),
                "execution_error": None,
            },
        )

    complete(transaction)


def _mark_execution_failed(
    *,
    approval_id: str,
    executor_id: str,
    error_type: str,
) -> None:
    """Record a sanitized execution failure when this executor owns it."""

    db = get_firestore_client()
    document = (
        db.collection(APPROVAL_COLLECTION)
        .document(approval_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def fail(
        active_transaction,
    ) -> None:
        snapshot = document.get(
            transaction=active_transaction
        )

        if not snapshot.exists:
            return

        record = snapshot.to_dict() or {}

        if record.get("execution_status") != EXECUTING:
            return

        if record.get("executed_by") != executor_id:
            return

        now = datetime.now(
            timezone.utc
        ).isoformat()

        active_transaction.update(
            document,
            {
                "execution_status": FAILED,
                "execution_updated_at": now,
                "execution_error": error_type,
                "executed_at": None,
            },
        )

    fail(transaction)


def _remote_mcp_url() -> str | None:
    value = os.getenv(
        MCP_URL_ENVIRONMENT_VARIABLE
    )

    if not value:
        return None

    return value.rstrip("/")


def _remote_mcp_audience(
    remote_url: str,
) -> str:
    configured_audience = os.getenv(
        MCP_AUDIENCE_ENVIRONMENT_VARIABLE
    )

    if configured_audience:
        return configured_audience.rstrip("/")

    parsed = urlsplit(remote_url)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "",
            "",
            "",
        )
    )


async def _call_mcp_submission_tool(
    arguments: dict[str, Any],
):
    """
    Call MCP locally or through authenticated Streamable HTTP.

    In Cloud Run, Application Default Credentials represent the
    membercare-api service account. The identity token is audience-bound
    to the MCP Cloud Run service and is never exposed to the LLM.
    """

    remote_url = _remote_mcp_url()

    async with AsyncExitStack() as stack:
        if remote_url:
            audience = _remote_mcp_audience(
                remote_url
            )

            token = await asyncio.to_thread(
                id_token.fetch_id_token,
                Request(),
                audience,
            )

            http_client = await stack.enter_async_context(
                httpx2.AsyncClient(
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        ),
                    },
                    timeout=httpx2.Timeout(
                        30.0,
                        read=300.0,
                    ),
                    follow_redirects=True,
                )
            )

            transport = streamable_http_client(
                remote_url,
                http_client=http_client,
            )

            client = await stack.enter_async_context(
                Client(transport)
            )
        else:
            client = await stack.enter_async_context(
                Client(
                    local_prior_authorization_mcp
                )
            )

        return await client.call_tool(
            "submit_prior_authorization",
            arguments,
        )


def _structured_mcp_result(
    structured_content: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = structured_content or {}

    nested_result = payload.get("result")

    if isinstance(nested_result, dict):
        return nested_result

    return payload


async def execute_approved_prior_authorization(
    *,
    approval_id: str,
    executor_id: str,
) -> dict[str, Any]:
    """
    Execute one approved prior-authorization action through MCP.

    The caller supplies only approval_id and authenticated executor_id.
    All action arguments are loaded from the approved Firestore record.
    """

    normalized_approval_id = approval_id.strip()
    normalized_executor_id = executor_id.strip()

    if not normalized_approval_id:
        raise ValueError("approval_id is required")

    if not normalized_executor_id:
        raise ValueError("executor_id is required")

    record = _claim_approved_execution(
        approval_id=normalized_approval_id,
        executor_id=normalized_executor_id,
    )

    action = record.get("action")

    if not isinstance(action, dict):
        _mark_execution_failed(
            approval_id=normalized_approval_id,
            executor_id=normalized_executor_id,
            error_type="approved_action_missing",
        )
        raise ApprovalExecutionError(
            "Approved action payload is missing."
        )

    arguments = {
        "approval_id": normalized_approval_id,
        "member_id": record.get("member_id", ""),
        "procedure_code": action.get(
            "procedure_code",
            "",
        ),
        "provider_id": action.get(
            "provider_id",
            "",
        ),
        "justification": action.get(
            "justification",
            "",
        ),
        "idempotency_key": normalized_approval_id,
    }

    try:
        result = await _call_mcp_submission_tool(
            arguments
        )

        if result.is_error is True:
            raise ApprovalExecutionError(
                "MCP submission returned an error result."
            )

        mcp_result = _structured_mcp_result(
            result.structured_content
        )

        if mcp_result.get("success") is not True:
            raise ApprovalExecutionError(
                "MCP submission did not report success."
            )

        if (
            mcp_result.get("approval_id")
            != normalized_approval_id
        ):
            raise ApprovalExecutionError(
                "MCP result approval_id does not match."
            )

        _mark_execution_completed(
            approval_id=normalized_approval_id,
            executor_id=normalized_executor_id,
            mcp_result=mcp_result,
        )

        return {
            "approval_id": normalized_approval_id,
            "execution_status": COMPLETED,
            "executed_by": normalized_executor_id,
            "external_reference": mcp_result.get(
                "external_reference"
            ),
            "submission_mode": mcp_result.get(
                "submission_mode"
            ),
            "message": (
                "Approved action executed through MCP."
            ),
        }

    except Exception as exc:
        _mark_execution_failed(
            approval_id=normalized_approval_id,
            executor_id=normalized_executor_id,
            error_type=type(exc).__name__,
        )
        raise