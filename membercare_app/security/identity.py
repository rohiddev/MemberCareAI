from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class AuthenticatedIdentity:
    user_id: str
    user_role: str
    member_id: str


# ============================================================
# LOCAL DEVELOPMENT IDENTITY STORE
# ============================================================
#
# For now this simulates an external Identity Provider.
#
# Later this will be replaced by validated identity from:
#
# - API Gateway
# - Cloud Run IAM
# - IAP
# - enterprise OAuth / OIDC
# - validated JWT claims
#
# The important architectural rule is:
#
# member_id is resolved SERVER-SIDE.
# The LLM and request JSON never decide member identity.
# ============================================================

DEV_IDENTITIES = {
    "dev-member-001": AuthenticatedIdentity(
        user_id="USER-001",
        user_role="member",
        member_id="MEM-001",
    ),
    "dev-member-999": AuthenticatedIdentity(
        user_id="USER-999",
        user_role="member",
        member_id="MEM-999",
    ),
}


async def get_authenticated_identity(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> AuthenticatedIdentity:
    """
    Resolve authenticated identity for the request.

    DEVELOPMENT IMPLEMENTATION ONLY.

    Expected header:

        Authorization: Bearer dev-member-001

    The API caller does not provide member_id directly.
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    prefix = "Bearer "

    if not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )

    token = authorization[len(prefix):].strip()

    identity = DEV_IDENTITIES.get(token)

    if not identity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    return identity