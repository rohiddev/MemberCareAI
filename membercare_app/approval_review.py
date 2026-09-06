from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from google.cloud import firestore

from membercare_app.config.firestore import get_firestore_client


APPROVAL_COLLECTION = "approval_requests"

PENDING_APPROVAL = "PENDING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

ReviewDecision = Literal[
    "APPROVED",
    "REJECTED",
]


class ApprovalReviewError(Exception):
    """Base error for deterministic approval review failures."""


class ApprovalNotFoundError(ApprovalReviewError):
    """Raised when an approval request does not exist."""


class ApprovalStateConflictError(ApprovalReviewError):
    """Raised when an approval is no longer pending review."""


class ApprovalReviewerConflictError(ApprovalReviewError):
    """Raised when the requester attempts to review their own request."""


def get_approval_request(
    approval_id: str,
) -> dict[str, Any]:
    """Retrieve one approval request for an authenticated reviewer."""

    normalized_approval_id = approval_id.strip()

    if not normalized_approval_id:
        raise ValueError("approval_id is required")

    snapshot = (
        get_firestore_client()
        .collection(APPROVAL_COLLECTION)
        .document(normalized_approval_id)
        .get()
    )

    if not snapshot.exists:
        raise ApprovalNotFoundError(
            f"Approval request '{normalized_approval_id}' was not found."
        )

    return snapshot.to_dict() or {}


def review_approval_request(
    *,
    approval_id: str,
    decision: ReviewDecision,
    reviewer_id: str,
    reviewer_role: str,
    review_comment: str | None = None,
) -> dict[str, Any]:
    """
    Approve or reject one pending request in a Firestore transaction.

    This function records a human decision only. Approval does not
    execute or submit the proposed action.
    """

    normalized_approval_id = approval_id.strip()
    normalized_reviewer_id = reviewer_id.strip()
    normalized_reviewer_role = reviewer_role.strip()
    normalized_decision = decision.strip().upper()
    normalized_comment = (
        review_comment.strip()
        if review_comment
        else None
    )

    if not normalized_approval_id:
        raise ValueError("approval_id is required")

    if not normalized_reviewer_id:
        raise ValueError("reviewer_id is required")

    if normalized_reviewer_role != "approval_reviewer":
        raise PermissionError(
            "Reviewer role is not authorized."
        )

    if normalized_decision not in {
        APPROVED,
        REJECTED,
    }:
        raise ValueError(
            "decision must be APPROVED or REJECTED"
        )

    db = get_firestore_client()
    document = (
        db.collection(APPROVAL_COLLECTION)
        .document(normalized_approval_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def apply_review(
        active_transaction,
    ) -> dict[str, Any]:
        snapshot = document.get(
            transaction=active_transaction
        )

        if not snapshot.exists:
            raise ApprovalNotFoundError(
                f"Approval request '{normalized_approval_id}' "
                "was not found."
            )

        record = snapshot.to_dict() or {}
        current_status = record.get("status")

        if current_status != PENDING_APPROVAL:
            raise ApprovalStateConflictError(
                "Approval request is no longer pending. "
                f"Current status: {current_status}."
            )

        requested_by = record.get(
            "requested_by_user_id"
        )

        if requested_by == normalized_reviewer_id:
            raise ApprovalReviewerConflictError(
                "The requester cannot review their own request."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        updates = {
            "status": normalized_decision,
            "updated_at": now,
            "reviewed_by": normalized_reviewer_id,
            "reviewed_by_role": normalized_reviewer_role,
            "reviewed_at": now,
            "review_comment": normalized_comment,

            # Human approval is not execution.
            "execution_status": "NOT_EXECUTED",
            "executed_at": None,
        }

        active_transaction.update(
            document,
            updates,
        )

        return {
            **record,
            **updates,
        }

    updated_record = apply_review(
        transaction
    )

    return {
        "approval_id": normalized_approval_id,
        "status": updated_record["status"],
        "reviewed_by": updated_record["reviewed_by"],
        "reviewed_at": updated_record["reviewed_at"],
        "review_comment": updated_record.get(
            "review_comment"
        ),
        "execution_status": updated_record[
            "execution_status"
        ],
        "message": (
            "The human review decision was recorded. "
            "No external action has been executed."
        ),
    }