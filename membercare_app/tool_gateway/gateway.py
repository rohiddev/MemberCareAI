import time
from typing import Any

from membercare_app.context.request_context import (
    get_member_id,
    get_request_id,
    get_user_id,
    get_user_role,
)
from membercare_app.evaluation.routing_tracker import record_agent
from membercare_app.evaluation.tool_tracker import record_tool
from membercare_app.observability.events import emit_event
from membercare_app.observability.tracing import get_tracer
from membercare_app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from membercare_app.reliability.retry import (
    RetryExhaustedError,
    execute_with_retry,
)
from membercare_app.reliability.timeout import (
    OperationTimeoutError,
    execute_with_timeout,
)
from membercare_app.tools.benefit_tools import get_member_benefits
from membercare_app.tools.approval_tools import (
    propose_prior_authorization,
)
from membercare_app.tools.claim_tools import get_claim_by_id
from membercare_app.tools.knowledge_tools import search_plan_knowledge
from membercare_app.tools.provider_tools import get_provider_network_status


tracer = get_tracer()


# ============================================================
# TOOL REGISTRY
# ============================================================
#
# Every enterprise capability that an agent may invoke
# must be explicitly registered here.
#
# Gemini cannot call arbitrary Python functions.
# ============================================================

TOOL_REGISTRY = {
    "get_claim_by_id": get_claim_by_id,
    "get_member_benefits": get_member_benefits,
    "get_provider_network_status": get_provider_network_status,
    "search_plan_knowledge": search_plan_knowledge,
    "propose_prior_authorization": propose_prior_authorization,
}


# ============================================================
# AGENT TOOL PERMISSIONS
# ============================================================
#
# Least privilege:
#
# Claims Agent
#   → claim facts only
#
# Benefits Agent
#   → member benefit facts
#   → enterprise plan/policy RAG
#
# Provider Agent
#   → provider network facts only
# ============================================================

AGENT_TOOL_PERMISSIONS = {
    "claims_agent": {
        "get_claim_by_id",
    },

    "benefits_agent": {
        "get_member_benefits",
        "search_plan_knowledge",
        "propose_prior_authorization",
    },

    "provider_agent": {
        "get_provider_network_status",
    },
}


# ============================================================
# RELIABILITY POLICY
# ============================================================
#
# Execution order:
#
# Circuit Breaker
#       ↓
# Retry / Backoff
#       ↓
# Timeout per attempt
#       ↓
# Enterprise Tool
#
# These controls are deterministic and outside Gemini.
# ============================================================

MAX_TOOL_ATTEMPTS = 3

INITIAL_RETRY_DELAY_SECONDS = 0.25

BACKOFF_MULTIPLIER = 2.0

TOOL_TIMEOUT_SECONDS = 3.0


RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OperationTimeoutError,
)


# ============================================================
# CIRCUIT BREAKERS
# ============================================================
#
# Each dependency has its own circuit breaker.
#
# A claims outage must not block:
#
# - benefits
# - provider
# - knowledge retrieval
# ============================================================

CIRCUIT_BREAKERS = {
    "get_claim_by_id": CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=5.0,
    ),

    "get_member_benefits": CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=5.0,
    ),

    "get_provider_network_status": CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=5.0,
    ),

    "search_plan_knowledge": CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=5.0,
    ),

    "propose_prior_authorization": CircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=5.0,
    ),
}


# ============================================================
# TOOL GATEWAY
# ============================================================

def execute_tool(
    agent_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute an enterprise capability through the
    MemberCareAI Tool Gateway.

    Responsibilities:

    1. Read trusted request context.
    2. Validate authenticated identity.
    3. Validate tool registration.
    4. Validate agent authorization.
    5. Record agent-routing evidence.
    6. Record tool-routing evidence.
    7. Check circuit-breaker state.
    8. Apply bounded retry/backoff.
    9. Apply timeout to each attempt.
    10. Execute the deterministic enterprise capability.
    11. Emit structured observability events.
    12. Create OpenTelemetry spans.
    13. Return a standard governed response.

    Gemini does not control:

    - identity
    - authorization
    - tool permissions
    - retries
    - timeouts
    - circuit breakers
    """

    start_time = time.perf_counter()

    # ========================================================
    # 1. LOAD TRUSTED REQUEST CONTEXT
    # ========================================================

    request_id = get_request_id()
    user_id = get_user_id()
    user_role = get_user_role()
    member_id = get_member_id()

    emit_event(
        "tool_call_started",
        request_id=request_id,
        agent_name=agent_name,
        tool_name=tool_name,
    )

    # ========================================================
    # 2. VALIDATE REQUEST ID
    # ========================================================

    if not request_id:

        return {
            "success": False,
            "gateway_status": "DENIED",
            "error": "request_id is missing",
        }

    # ========================================================
    # 3. VALIDATE USER ID
    # ========================================================

    if not user_id:

        emit_event(
            "tool_call_denied",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="user_id_missing",
        )

        return {
            "success": False,
            "gateway_status": "DENIED",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": "user_id is missing",
        }

    # ========================================================
    # 4. VALIDATE USER ROLE
    # ========================================================

    if not user_role:

        emit_event(
            "tool_call_denied",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="user_role_missing",
        )

        return {
            "success": False,
            "gateway_status": "DENIED",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": "user_role is missing",
        }

    # ========================================================
    # 5. VALIDATE MEMBER ID
    # ========================================================

    if not member_id:

        emit_event(
            "tool_call_denied",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="member_id_missing",
        )

        return {
            "success": False,
            "gateway_status": "DENIED",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": "member_id is missing",
        }

    # ========================================================
    # 6. VALIDATE TOOL REGISTRATION
    # ========================================================

    tool = TOOL_REGISTRY.get(
        tool_name
    )

    if tool is None:

        emit_event(
            "tool_call_denied",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="tool_not_registered",
        )

        return {
            "success": False,
            "gateway_status": "DENIED",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": "tool is not registered",
        }

    # ========================================================
    # 7. VALIDATE AGENT PERMISSION
    # ========================================================

    allowed_tools = AGENT_TOOL_PERMISSIONS.get(
        agent_name,
        set(),
    )

    if tool_name not in allowed_tools:

        emit_event(
            "tool_call_denied",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="agent_not_authorized",
        )

        return {
            "success": False,
            "gateway_status": "DENIED",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": (
                f"agent '{agent_name}' is not authorized "
                f"to use tool '{tool_name}'"
            ),
        }

    # ========================================================
    # 8. GET CIRCUIT BREAKER
    # ========================================================

    breaker = CIRCUIT_BREAKERS.get(
        tool_name
    )

    if breaker is None:

        emit_event(
            "tool_call_failed",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="circuit_breaker_missing",
        )

        return {
            "success": False,
            "gateway_status": "ERROR",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": (
                "Circuit breaker is not configured "
                "for this tool."
            ),
        }

    # ========================================================
    # 9. RECORD ROUTING EVIDENCE
    # ========================================================
    #
    # These are recorded only after:
    #
    # - trusted context validation
    # - tool registration
    # - agent authorization
    #
    # This means the evaluation framework records only
    # legitimate governed execution attempts.
    # ========================================================

    record_agent(
        request_id=request_id,
        agent_name=agent_name,
    )

    record_tool(
        request_id=request_id,
        tool_name=tool_name,
    )

    # ========================================================
    # 10. RETRY CALLBACK
    # ========================================================

    def on_retry(
        attempt: int,
        exception: Exception,
        delay: float,
    ) -> None:

        emit_event(
            "tool_retry_scheduled",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            failed_attempt=attempt,
            error_type=type(
                exception
            ).__name__,
            retry_delay_seconds=delay,
        )

    # ========================================================
    # 11. ONE TIMED TOOL ATTEMPT
    # ========================================================
    #
    # Every individual dependency attempt receives its own
    # timeout.
    #
    # Example:
    #
    # Attempt 1
    #    ↓
    # timeout
    #    ↓
    # retry
    #
    # Attempt 2
    #    ↓
    # success
    # ========================================================

    def invoke_one_attempt() -> Any:

        return execute_with_timeout(
            lambda: tool(
                **arguments,
            ),
            timeout_seconds=TOOL_TIMEOUT_SECONDS,
        )

    # ========================================================
    # 12. RETRY BLOCK
    # ========================================================

    def invoke_with_retry() -> Any:

        return execute_with_retry(
            invoke_one_attempt,
            max_attempts=MAX_TOOL_ATTEMPTS,
            initial_delay_seconds=(
                INITIAL_RETRY_DELAY_SECONDS
            ),
            backoff_multiplier=(
                BACKOFF_MULTIPLIER
            ),
            retryable_exceptions=(
                RETRYABLE_EXCEPTIONS
            ),
            on_retry=on_retry,
        )

    # ========================================================
    # 13. CIRCUIT BREAKER + RETRY + TIMEOUT + TOOL
    # ========================================================

    try:

        with tracer.start_as_current_span(
            f"membercare.tool.{tool_name}"
        ) as span:

            span.set_attribute(
                "membercare.request_id",
                request_id,
            )

            span.set_attribute(
                "membercare.agent_name",
                agent_name,
            )

            span.set_attribute(
                "membercare.tool_name",
                tool_name,
            )

            span.set_attribute(
                "membercare.retry.max_attempts",
                MAX_TOOL_ATTEMPTS,
            )

            span.set_attribute(
                "membercare.timeout.seconds",
                TOOL_TIMEOUT_SECONDS,
            )

            span.set_attribute(
                "membercare.circuit.state.before",
                breaker.state,
            )

            result = breaker.execute(
                invoke_with_retry,
                failure_exceptions=(
                    RetryExhaustedError,
                    ConnectionError,
                    TimeoutError,
                    OperationTimeoutError,
                ),
            )

            span.set_attribute(
                "membercare.circuit.state.after",
                breaker.state,
            )

            span.set_attribute(
                "membercare.success",
                True,
            )

    # ========================================================
    # 14. CIRCUIT OPEN — FAIL FAST
    # ========================================================

    except CircuitBreakerOpenError as exc:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        emit_event(
            "tool_circuit_open",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            circuit_state=breaker.state,
            retry_after_seconds=round(
                exc.retry_after_seconds,
                2,
            ),
            latency_ms=latency_ms,
        )

        emit_event(
            "tool_call_failed",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="circuit_open",
            latency_ms=latency_ms,
        )

        return {
            "success": False,
            "gateway_status": "CIRCUIT_OPEN",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": (
                "Tool dependency is temporarily unavailable."
            ),
            "retry_after_seconds": round(
                exc.retry_after_seconds,
                2,
            ),
        }

    # ========================================================
    # 15. RETRIES EXHAUSTED
    # ========================================================

    except RetryExhaustedError as exc:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        last_exception = (
            exc.last_exception
        )

        if isinstance(
            last_exception,
            OperationTimeoutError,
        ):
            failure_reason = (
                "timeout_retry_exhausted"
            )
        else:
            failure_reason = (
                "retry_exhausted"
            )

        emit_event(
            "tool_retry_exhausted",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            attempts=exc.attempts,
            error_type=type(
                last_exception
            ).__name__,
            circuit_state=breaker.state,
            latency_ms=latency_ms,
        )

        if breaker.state == CircuitBreaker.OPEN:

            emit_event(
                "tool_circuit_opened",
                request_id=request_id,
                agent_name=agent_name,
                tool_name=tool_name,
                circuit_state=breaker.state,
            )

        emit_event(
            "tool_call_failed",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason=failure_reason,
            latency_ms=latency_ms,
            error_type=type(
                last_exception
            ).__name__,
        )

        return {
            "success": False,
            "gateway_status": "ERROR",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": (
                "Tool dependency remained unavailable "
                "after reliability attempts."
            ),
            "attempts": exc.attempts,
            "failure_reason": failure_reason,
            "circuit_state": breaker.state,
        }

    # ========================================================
    # 16. NON-RETRYABLE FAILURE
    # ========================================================

    except Exception as exc:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        emit_event(
            "tool_call_failed",
            request_id=request_id,
            agent_name=agent_name,
            tool_name=tool_name,
            reason="non_retryable_exception",
            latency_ms=latency_ms,
            error_type=type(
                exc
            ).__name__,
        )

        return {
            "success": False,
            "gateway_status": "ERROR",
            "request_id": request_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "error": str(
                exc
            ),
            "circuit_state": breaker.state,
        }

    # ========================================================
    # 17. SUCCESS OBSERVABILITY
    # ========================================================

    latency_ms = round(
        (
            time.perf_counter()
            - start_time
        )
        * 1000,
        2,
    )

    emit_event(
        "tool_call_completed",
        request_id=request_id,
        agent_name=agent_name,
        tool_name=tool_name,
        gateway_status="SUCCESS",
        circuit_state=breaker.state,
        latency_ms=latency_ms,
    )

    # ========================================================
    # 18. STANDARD SUCCESS RESPONSE
    # ========================================================

    return {
        "success": True,
        "gateway_status": "SUCCESS",
        "request_id": request_id,
        "agent_name": agent_name,
        "tool_name": tool_name,
        "circuit_state": breaker.state,
        "result": result,
    }