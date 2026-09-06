import time
import uuid

from membercare_app.agent_runtime_executor import execute_runtime_agent
from membercare_app.context.request_context import set_request_context
from membercare_app.memory.session_memory import (
    add_message,
    ensure_session,
    get_recent_messages,
)
from membercare_app.observability.events import emit_event
from membercare_app.observability.tracing import get_tracer
from membercare_app.policy.policy_engine import check_clinical_advice_policy


tracer = get_tracer()


async def execute_agent(
    message: str,
    session_id: str,
    user_id: str,
    user_role: str,
    member_id: str,
) -> tuple[str, str]:
    """
    Execute one MemberCareAI request.

    The outer orchestrator owns:

    - request lifecycle
    - trusted request context
    - request-level policy enforcement
    - durable conversation memory
    - Agent Runtime invocation
    - persistence
    - observability

    The Agent Runtime executor owns:

    - ADK Runner
    - Supervisor execution
    - specialist-agent execution
    - inner agent loop
    """

    request_start = time.perf_counter()

    request_id = str(
        uuid.uuid4()
    )

    # ========================================================
    # ROOT REQUEST TRACE
    # ========================================================

    with tracer.start_as_current_span(
        "membercare.request"
    ) as request_span:

        request_span.set_attribute(
            "membercare.request_id",
            request_id,
        )

        request_span.set_attribute(
            "membercare.session_id",
            session_id,
        )

        request_span.set_attribute(
            "membercare.user_role",
            user_role,
        )

        # ====================================================
        # 1. REQUEST STARTED
        # ====================================================

        emit_event(
            "request_started",
            request_id=request_id,
            session_id=session_id,
            user_role=user_role,
        )

        # ====================================================
        # 2. ESTABLISH TRUSTED REQUEST CONTEXT
        # ====================================================

        set_request_context(
            request_id=request_id,
            user_id=user_id,
            user_role=user_role,
            member_id=member_id,
            session_id=session_id,
        )

        emit_event(
            "request_context_established",
            request_id=request_id,
            session_id=session_id,
            user_role=user_role,
        )

        # ====================================================
        # 3. REQUEST-LEVEL POLICY CHECK
        # ====================================================

        emit_event(
            "policy_check_started",
            request_id=request_id,
            policy_name="NO_CLINICAL_ADVICE",
        )

        policy_decision = (
            check_clinical_advice_policy(
                message
            )
        )

        # ====================================================
        # 4. POLICY DENIED
        # ====================================================

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

            request_span.set_attribute(
                "membercare.policy.denied",
                True,
            )

            request_span.set_attribute(
                "membercare.policy.name",
                policy_decision.policy_name,
            )

            # ================================================
            # Persist denied interaction
            # ================================================

            ensure_session(
                session_id=session_id,
                user_id=user_id,
                member_id=member_id,
            )

            denial_response = (
                "I can help with administrative healthcare "
                "questions such as claims, benefits, and "
                "provider-network information, but I cannot "
                "provide diagnosis or treatment recommendations. "
                "For medical advice, please contact a qualified "
                "healthcare professional."
            )

            add_message(
                session_id=session_id,
                role="user",
                content=message,
            )

            add_message(
                session_id=session_id,
                role="assistant",
                content=denial_response,
            )

            latency_ms = round(
                (
                    time.perf_counter()
                    - request_start
                )
                * 1000,
                2,
            )

            emit_event(
                "request_completed",
                request_id=request_id,
                session_id=session_id,
                success=True,
                policy_denied=True,
                latency_ms=latency_ms,
            )

            return (
                denial_response,
                request_id,
            )

        # ====================================================
        # 5. POLICY ALLOWED
        # ====================================================

        emit_event(
            "policy_allowed",
            request_id=request_id,
            policy_name=(
                policy_decision.policy_name
            ),
        )

        request_span.set_attribute(
            "membercare.policy.denied",
            False,
        )

        # ====================================================
        # 6. ENSURE DURABLE SESSION
        # ====================================================

        ensure_session(
            session_id=session_id,
            user_id=user_id,
            member_id=member_id,
        )

        # ====================================================
        # 7. LOAD MEMORY
        # ====================================================

        with tracer.start_as_current_span(
            "membercare.memory.load"
        ):

            recent_messages = (
                get_recent_messages(
                    session_id=session_id,
                    limit=6,
                )
            )

        emit_event(
            "memory_loaded",
            request_id=request_id,
            session_id=session_id,
            message_count=len(
                recent_messages
            ),
        )

        # ====================================================
        # 8. BUILD RUNTIME MESSAGE
        # ====================================================

        history_lines = []

        for memory_message in recent_messages:

            role = memory_message.get(
                "role",
                "unknown",
            )

            content = memory_message.get(
                "content",
                "",
            )

            history_lines.append(
                f"{role}: {content}"
            )

        if history_lines:

            runtime_message = (
                "Recent conversation history:\n"
                + "\n".join(
                    history_lines
                )
                + "\n\n"
                + "Current member request:\n"
                + message
            )

        else:

            runtime_message = message

        # ====================================================
        # 9. INVOKE AGENT RUNTIME
        # ====================================================

        emit_event(
            "agent_runtime_started",
            request_id=request_id,
            session_id=session_id,
        )

        runtime_start = time.perf_counter()

        # IMPORTANT:
        #
        # member_id is NOT passed directly into the Agent
        # Runtime.
        #
        # Member identity has already been established in the
        # trusted request context above.
        #
        # Specialist tools retrieve it through:
        #
        #     get_member_id()
        #
        # This keeps identity outside model-controlled data.
        #

        final_text = await execute_runtime_agent(
            message=runtime_message,
            session_id=session_id,
            user_id=user_id,
        )

        runtime_latency_ms = round(
            (
                time.perf_counter()
                - runtime_start
            )
            * 1000,
            2,
        )

        emit_event(
            "agent_runtime_completed",
            request_id=request_id,
            session_id=session_id,
            latency_ms=runtime_latency_ms,
        )

        # ====================================================
        # 10. PERSIST MEMORY
        # ====================================================

        with tracer.start_as_current_span(
            "membercare.memory.persist"
        ):

            add_message(
                session_id=session_id,
                role="user",
                content=message,
            )

            add_message(
                session_id=session_id,
                role="assistant",
                content=final_text,
            )

        emit_event(
            "memory_persisted",
            request_id=request_id,
            session_id=session_id,
        )

        # ====================================================
        # 11. REQUEST COMPLETED
        # ====================================================

        latency_ms = round(
            (
                time.perf_counter()
                - request_start
            )
            * 1000,
            2,
        )

        emit_event(
            "request_completed",
            request_id=request_id,
            session_id=session_id,
            success=True,
            latency_ms=latency_ms,
        )

        return (
            final_text,
            request_id,
        )