from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class AuthenticatedExecutor:
    executor_id: str
    executor_role: str


# ============================================================
# LOCAL DEVELOPMENT EXECUTOR IDENTITY STORE
# ============================================================
#
# DEVELOPMENT IMPLEMENTATION ONLY.
#
# This identity is deliberately separate from both member identity
# and reviewer identity. An executor does not receive a member_id and
# cannot approve or alter the stored action payload.
#
# Replace this token map with Cloud Run service-to-service IAM and
# validated workload identity before production use.
# ============================================================

DEV_EXECUTORS = {
    "dev-executor-001": AuthenticatedExecutor(
        executor_id="EXECUTOR-001",
        executor_role="approval_executor",
    ),
}


async def get_authenticated_executor(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> AuthenticatedExecutor:
    """
    Resolve an execution-service identity.

    DEVELOPMENT IMPLEMENTATION ONLY.

    Expected application header:

        Authorization: Bearer dev-executor-001

    When Cloud Run IAM is enabled, use X-Serverless-Authorization for
    Cloud Run and reserve Authorization for this application identity.
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Executor authorization header is required",
        )

    prefix = "Bearer "

    if not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Executor bearer token is required",
        )

    token = authorization[len(prefix):].strip()
    executor = DEV_EXECUTORS.get(token)

    if not executor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid executor authentication token",
        )

    if executor.executor_role != "approval_executor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Executor role is not authorized",
        )

    return executor