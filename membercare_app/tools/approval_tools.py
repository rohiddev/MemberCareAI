from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from membercare_app.config.firestore import get_firestore_client
from membercare_app.context.request_context import (
    get_member_id,
    get_request_id,
    get_session_id,
    get_user_id,
    get_user_role,
)


APPROVAL_COLLECTION = "approval_requests"
PENDING_APPROVAL = "PENDING_APPROVAL"


def _required_text(
    value: str,
    field_name: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} is required"
        )

    return normalized


def _approval_id(
    *,
    request_id: str,
    member_id: str,
    procedure_code: str,
    provider_id: str,
) -> str:
    """
    Produce an idempotent approval ID.

    Gateway retries must not create duplicate approval requests.
    """

    source = "|".join(
        [
            request_id,
            member_id,
            procedure_code,
            provider_id,
        ]
    )

    digest = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()[:24]

    return f"approval-{digest}"


def propose_prior_authorization(
    procedure_code: str,
    provider_id: str,
    justification: str,
) -> dict[str, Any]:
    """
    Create a prior-authorization proposal for human review.

    This tool does not submit anything to a payer or external system.
    It only records a governed PENDING_APPROVAL request.

    The authenticated member identity comes exclusively from trusted
    request context.
    """

    request_id = get_request_id()
    user_id = get_user_id()
    user_role = get_user_role()
    member_id = get_member_id()
    session_id = get_session_id()

    required_context = {
        "request_id": request_id,
        "user_id": user_id,
        "user_role": user_role,
        "member_id": member_id,
        "session_id": session_id,
    }

    missing_context = [
        key
        for key, value in required_context.items()
        if not value
    ]

    if missing_context:
        return {
            "created": False,
            "approval_required": True,
            "error": (
                "Trusted request context is incomplete: "
                + ", ".join(missing_context)
            ),
        }

    try:
        normalized_procedure_code = _required_text(
            procedure_code,
            "procedure_code",
        )
        normalized_provider_id = _required_text(
            provider_id,
            "provider_id",
        )
        normalized_justification = _required_text(
            justification,
            "justification",
        )
    except ValueError as exc:
        return {
            "created": False,
            "approval_required": True,
            "error": str(exc),
        }

    approval_id = _approval_id(
        request_id=str(request_id),
        member_id=str(member_id),
        procedure_code=normalized_procedure_code,
        provider_id=normalized_provider_id,
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    record = {
        "approval_id": approval_id,
        "action_type": "PRIOR_AUTHORIZATION",
        "status": PENDING_APPROVAL,
        "approval_required": True,
        "request_id": str(request_id),
        "session_id": str(session_id),
        "requested_by_user_id": str(user_id),
        "requested_by_user_role": str(user_role),
        "member_id": str(member_id),
        "action": {
            "procedure_code": normalized_procedure_code,
            "provider_id": normalized_provider_id,
            "justification": normalized_justification,
        },
        "created_at": now,
        "updated_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_comment": None,
        "executed_at": None,
        "execution_status": "NOT_EXECUTED",
    }

    db = get_firestore_client()
    document = (
        db.collection(APPROVAL_COLLECTION)
        .document(approval_id)
    )

    # The deterministic document ID makes gateway retries idempotent.
    existing = document.get()

    if existing.exists:
        existing_record = existing.to_dict() or {}

        return {
            "created": False,
            "idempotent_replay": True,
            "approval_required": True,
            "approval_id": approval_id,
            "status": existing_record.get(
                "status",
                PENDING_APPROVAL,
            ),
            "message": (
                "An approval request already exists "
                "for this action."
            ),
        }

    document.set(record)

    return {
        "created": True,
        "idempotent_replay": False,
        "approval_required": True,
        "approval_id": approval_id,
        "status": PENDING_APPROVAL,
        "message": (
            "The prior-authorization proposal was created "
            "and is waiting for human approval. "
            "No external action has been executed."
        ),
    }