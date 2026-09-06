from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class AuthenticatedReviewer:
    reviewer_id: str
    reviewer_role: str


# ============================================================
# LOCAL DEVELOPMENT REVIEWER IDENTITY STORE
# ============================================================
#
# DEVELOPMENT IMPLEMENTATION ONLY.
#
# This identity store is deliberately separate from member identity.
# A reviewer does not receive or choose a member_id.
#
# Replace this with validated enterprise OAuth/OIDC/JWT claims before
# production use. The validated claims should establish both reviewer
# identity and an authorized reviewer role.
# ============================================================

DEV_REVIEWERS = {
    "dev-reviewer-001": AuthenticatedReviewer(
        reviewer_id="REVIEWER-001",
        reviewer_role="approval_reviewer",
    ),
}


async def get_authenticated_reviewer(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> AuthenticatedReviewer:
    """
    Resolve a human reviewer identity for an approval API request.

    DEVELOPMENT IMPLEMENTATION ONLY.

    Expected application header:

        Authorization: Bearer dev-reviewer-001

    When Cloud Run IAM is enabled, use X-Serverless-Authorization for
    Cloud Run and reserve Authorization for this application identity.
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reviewer authorization header is required",
        )

    prefix = "Bearer "

    if not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reviewer bearer token is required",
        )

    token = authorization[len(prefix):].strip()
    reviewer = DEV_REVIEWERS.get(token)

    if not reviewer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reviewer authentication token",
        )

    if reviewer.reviewer_role != "approval_reviewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer role is not authorized",
        )

    return reviewer