from typing import Any

from membercare_app.config.firestore import get_firestore_client
from membercare_app.context.request_context import get_member_id


def get_member_benefits() -> dict[str, Any]:
    """
    Retrieve benefit-plan information for the authenticated member.

    Returns:
        Member plan information including plan name,
        plan type, individual deductible, and coinsurance.

    Authorization is based on trusted member context.
    """

    authenticated_member_id = get_member_id()

    if not authenticated_member_id:
        return {
            "found": False,
            "authorized": False,
            "error": "authenticated member context is missing",
        }

    db = get_firestore_client()

    # ========================================================
    # 1. RETRIEVE AUTHENTICATED MEMBER
    # ========================================================

    member_document = (
        db.collection("members")
        .document(authenticated_member_id)
        .get()
    )

    if not member_document.exists:
        return {
            "found": False,
            "authorized": True,
            "error": "member not found",
        }

    member = member_document.to_dict()

    plan_id = member.get("plan_id")

    if not plan_id:
        return {
            "found": False,
            "authorized": True,
            "error": "member has no assigned plan",
        }

    # ========================================================
    # 2. RETRIEVE MEMBER PLAN
    # ========================================================

    plan_document = (
        db.collection("plans")
        .document(plan_id)
        .get()
    )

    if not plan_document.exists:
        return {
            "found": False,
            "authorized": True,
            "error": "benefit plan not found",
        }

    plan = plan_document.to_dict()

    # ========================================================
    # 3. RETURN AUTHORIZED BENEFIT FACTS
    # ========================================================

    return {
        "found": True,
        "authorized": True,
        "member_id": authenticated_member_id,
        "plan": plan,
    }