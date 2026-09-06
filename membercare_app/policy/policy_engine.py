from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    policy_name: str
    reason: str | None = None


# ============================================================
# HEALTHCARE POLICY RULES
# ============================================================


def check_clinical_advice_policy(
    request_text: str,
) -> PolicyDecision:
    """
    MemberCareAI is an administrative healthcare assistant.

    It must not provide diagnosis or treatment advice.
    """

    normalized = request_text.lower()

    prohibited_terms = (
        "diagnose me",
        "what disease do i have",
        "what medication should i take",
        "what medicine should i take",
        "should i take",
        "what treatment should i get",
        "how should i treat",
    )

    for term in prohibited_terms:
        if term in normalized:
            return PolicyDecision(
                allowed=False,
                policy_name="NO_CLINICAL_ADVICE",
                reason=(
                    "MemberCareAI does not provide diagnosis "
                    "or treatment recommendations."
                ),
            )

    return PolicyDecision(
        allowed=True,
        policy_name="NO_CLINICAL_ADVICE",
    )


def check_member_access_policy(
    authenticated_member_id: str,
    resource_member_id: str,
) -> PolicyDecision:
    """
    Prevent one authenticated member from accessing
    another member's healthcare data.
    """

    if (
        authenticated_member_id
        != resource_member_id
    ):
        return PolicyDecision(
            allowed=False,
            policy_name="MEMBER_RESOURCE_OWNERSHIP",
            reason=(
                "Authenticated member is not authorized "
                "to access this resource."
            ),
        )

    return PolicyDecision(
        allowed=True,
        policy_name="MEMBER_RESOURCE_OWNERSHIP",
    )


def check_network_coverage_policy(
    network_status: str,
) -> PolicyDecision:
    """
    Prevent provider network status from being interpreted
    as guaranteed service coverage or cost.
    """

    normalized = (
        network_status
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )

    if normalized.strip() == "in network":
        return PolicyDecision(
            allowed=True,
            policy_name="NETWORK_NOT_COVERAGE",
            reason=(
                "Provider is in network, but network status "
                "does not guarantee service coverage or cost."
            ),
        )

    return PolicyDecision(
        allowed=True,
        policy_name="NETWORK_NOT_COVERAGE",
    )