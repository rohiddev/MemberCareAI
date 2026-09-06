from membercare_app.config.firestore import get_firestore_client
from membercare_app.context.request_context import (
    get_member_id,
    get_request_id,
)
from membercare_app.observability.events import emit_event
from membercare_app.policy.policy_engine import (
    check_member_access_policy,
)


# ============================================================
# CLAIM LOOKUP
# ============================================================

def get_claim_by_id(
    claim_id: str,
) -> dict:
    """
    Retrieve one healthcare claim.

    Security model:

    - Authenticated member identity comes from trusted
      RequestContext.
    - The LLM does not provide or choose member_id.
    - The claim is retrieved from Firestore.
    - The Policy Engine verifies resource ownership.
    - Claim details are returned only after authorization.

    This keeps authorization deterministic and outside Gemini.
    """

    request_id = get_request_id()

    authenticated_member_id = (
        get_member_id()
    )

    # ========================================================
    # 1. REQUIRE AUTHENTICATED MEMBER CONTEXT
    # ========================================================

    if not authenticated_member_id:

        emit_event(
            "policy_denied",
            request_id=request_id,
            policy_name=(
                "MEMBER_RESOURCE_OWNERSHIP"
            ),
            reason=(
                "authenticated_member_missing"
            ),
        )

        return {
            "found": False,
            "authorized": False,
            "error": (
                "Authenticated member context "
                "is missing."
            ),
        }

    # ========================================================
    # 2. VALIDATE CLAIM ID
    # ========================================================

    if not claim_id:

        return {
            "found": False,
            "authorized": False,
            "error": "claim_id is required",
        }

    # ========================================================
    # 3. LOAD CLAIM FROM FIRESTORE
    # ========================================================

    db = get_firestore_client()

    claim_ref = (
        db.collection("claims")
        .document(claim_id)
    )

    try:
        claim_snapshot = (
            claim_ref.get()
        )

    except Exception as exc:

        # ----------------------------------------------------
        # Diagnostic event:
        #
        # This helps identify whether a managed Agent Runtime
        # failure is caused by:
        #
        # - Firestore IAM
        # - wrong database access
        # - missing permission
        # - backend connectivity
        #
        # Do not include claim contents or other PHI-like data
        # in this event.
        # ----------------------------------------------------

        emit_event(
            "claim_firestore_error",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

        raise

    # ========================================================
    # 4. CLAIM NOT FOUND
    # ========================================================

    if not claim_snapshot.exists:

        return {
            "found": False,
            "authorized": False,
            "claim_id": claim_id,
            "error": "Claim not found",
        }

    claim = (
        claim_snapshot.to_dict()
    )

    if claim is None:

        return {
            "found": False,
            "authorized": False,
            "claim_id": claim_id,
            "error": "Claim data unavailable",
        }

    # ========================================================
    # 5. GET RESOURCE OWNER
    # ========================================================

    resource_member_id = (
        claim.get("member_id")
    )

    if not resource_member_id:

        emit_event(
            "policy_denied",
            request_id=request_id,
            policy_name=(
                "MEMBER_RESOURCE_OWNERSHIP"
            ),
            reason=(
                "claim_resource_owner_missing"
            ),
        )

        return {
            "found": True,
            "authorized": False,
            "claim_id": claim_id,
            "error": (
                "Claim ownership information "
                "is unavailable."
            ),
        }

    # ========================================================
    # 6. RESOURCE-LEVEL POLICY CHECK
    # ========================================================

    emit_event(
        "policy_check_started",
        request_id=request_id,
        policy_name=(
            "MEMBER_RESOURCE_OWNERSHIP"
        ),
    )

    policy_decision = (
        check_member_access_policy(
            authenticated_member_id=(
                authenticated_member_id
            ),
            resource_member_id=(
                resource_member_id
            ),
        )
    )

    # ========================================================
    # 7. ACCESS DENIED
    # ========================================================

    if not policy_decision.allowed:

        emit_event(
            "policy_denied",
            request_id=request_id,
            policy_name=(
                policy_decision.policy_name
            ),
            reason=(
                policy_decision.reason
            ),
        )

        # IMPORTANT:
        #
        # Do not return protected claim facts when
        # authorization fails.
        #
        # Do not expose:
        #
        # - billed amount
        # - allowed amount
        # - service/procedure
        # - provider information
        # - plan-paid amount
        # - member responsibility
        #

        return {
            "found": True,
            "authorized": False,
            "claim_id": claim_id,
            "error": (
                "Access to this claim was denied."
            ),
        }

    # ========================================================
    # 8. ACCESS ALLOWED
    # ========================================================

    emit_event(
        "policy_allowed",
        request_id=request_id,
        policy_name=(
            policy_decision.policy_name
        ),
    )

    # ========================================================
    # 9. RETURN AUTHORIZED CLAIM FACTS
    # ========================================================

    return {
        "found": True,
        "authorized": True,
        "claim": claim,
    }