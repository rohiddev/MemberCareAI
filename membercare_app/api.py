from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from membercare_app.approval_review import (
    ApprovalNotFoundError,
    ApprovalReviewerConflictError,
    ApprovalStateConflictError,
    get_approval_request,
    review_approval_request,
)
from membercare_app.approval_executor import (
    ApprovalExecutionError,
    ApprovalExecutionNotFoundError,
    ApprovalExecutionStateConflictError,
    execute_approved_prior_authorization,
)
from membercare_app.orchestrator import execute_agent
from membercare_app.security.identity import (
    AuthenticatedIdentity,
    get_authenticated_identity,
)
from membercare_app.security.reviewer_identity import (
    AuthenticatedReviewer,
    get_authenticated_reviewer,
)
from membercare_app.security.executor_identity import (
    AuthenticatedExecutor,
    get_authenticated_executor,
)


app = FastAPI(
    title="MemberCareAI",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
    )
    session_id: str = Field(
        min_length=1,
    )


class ChatResponse(BaseModel):
    request_id: str
    answer: str


class ApprovalReviewRequest(BaseModel):
    decision: Literal[
        "APPROVED",
        "REJECTED",
    ]
    review_comment: str | None = Field(
        default=None,
        max_length=2000,
    )


class ApprovalReviewResponse(BaseModel):
    approval_id: str
    status: str
    reviewed_by: str
    reviewed_at: str
    review_comment: str | None
    execution_status: str
    message: str


class ApprovalExecutionResponse(BaseModel):
    approval_id: str
    execution_status: str
    executed_by: str
    external_reference: str | None
    submission_mode: str | None
    message: str


class ApprovalDetailResponse(BaseModel):
    approval_id: str
    action_type: str
    status: str
    approval_required: bool
    request_id: str
    session_id: str
    requested_by_user_id: str
    requested_by_user_role: str
    member_id: str
    action: dict[str, Any]
    created_at: str
    updated_at: str
    reviewed_by: str | None
    reviewed_at: str | None
    review_comment: str | None
    execution_status: str
    executed_at: str | None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "MemberCareAI",
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    identity: AuthenticatedIdentity = Depends(
        get_authenticated_identity,
    ),
) -> ChatResponse:
    answer, request_id = await execute_agent(
        message=request.message,
        session_id=request.session_id,
        user_id=identity.user_id,
        user_role=identity.user_role,
        member_id=identity.member_id,
    )

    return ChatResponse(
        request_id=request_id,
        answer=answer,
    )


@app.get(
    "/approvals/{approval_id}",
    response_model=ApprovalDetailResponse,
)
async def get_approval_for_review(
    approval_id: str,
    reviewer: AuthenticatedReviewer = Depends(
        get_authenticated_reviewer,
    ),
) -> ApprovalDetailResponse:
    # Resolving the dependency establishes the authorized reviewer.
    # The reviewer object is intentionally not used to filter by member.
    _ = reviewer

    try:
        record = get_approval_request(
            approval_id
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ApprovalDetailResponse(
        **record
    )


@app.post(
    "/approvals/{approval_id}/review",
    response_model=ApprovalReviewResponse,
)
async def review_approval(
    approval_id: str,
    request: ApprovalReviewRequest,
    reviewer: AuthenticatedReviewer = Depends(
        get_authenticated_reviewer,
    ),
) -> ApprovalReviewResponse:
    try:
        result = review_approval_request(
            approval_id=approval_id,
            decision=request.decision,
            reviewer_id=reviewer.reviewer_id,
            reviewer_role=reviewer.reviewer_role,
            review_comment=request.review_comment,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ApprovalStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ApprovalReviewerConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ApprovalReviewResponse(
        **result
    )


@app.post(
    "/approvals/{approval_id}/execute",
    response_model=ApprovalExecutionResponse,
)
async def execute_approval(
    approval_id: str,
    executor: AuthenticatedExecutor = Depends(
        get_authenticated_executor,
    ),
) -> ApprovalExecutionResponse:
    """
    Execute one approved action through the deterministic MCP path.

    The endpoint accepts no action payload. All execution fields are
    loaded from the approved Firestore record.
    """

    try:
        result = await execute_approved_prior_authorization(
            approval_id=approval_id,
            executor_id=executor.executor_id,
        )
    except ApprovalExecutionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ApprovalExecutionStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ApprovalExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Approved action execution failed. "
                "Review the execution audit record."
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The execution dependency was unavailable. "
                "Review the execution audit record."
            ),
        ) from exc

    return ApprovalExecutionResponse(
        **result
    )