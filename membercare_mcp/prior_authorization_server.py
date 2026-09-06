from __future__ import annotations

import hashlib
import re
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


mcp = MCPServer(
    "membercare-prior-authorization"
)


PROCEDURE_CODE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9.-]{1,31}$"
)

PROVIDER_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$"
)


def _required_text(
    value: str,
    field_name: str,
    *,
    max_length: int,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} is required"
        )

    if len(normalized) > max_length:
        raise ValueError(
            f"{field_name} exceeds {max_length} characters"
        )

    return normalized


def _external_reference(
    idempotency_key: str,
) -> str:
    digest = hashlib.sha256(
        idempotency_key.encode("utf-8")
    ).hexdigest()[:20]

    return f"PA-SIM-{digest.upper()}"


@mcp.tool()
def submit_prior_authorization(
    approval_id: str,
    member_id: str,
    procedure_code: str,
    provider_id: str,
    justification: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """
    Submit an already-approved prior-authorization request.

    This implementation is a deterministic external-payer simulator.
    It does not make a real healthcare or payer submission.

    The caller must be the governed MemberCareAI executor. The executor
    must load the approved payload from Firestore and must not accept
    replacement action parameters from an end user or language model.

    Args:
        approval_id: Governed MemberCareAI approval identifier.
        member_id: Trusted member identifier from the approved record.
        procedure_code: Procedure code from the approved action.
        provider_id: Provider identifier from the approved action.
        justification: Justification from the approved action.
        idempotency_key: Stable key for safe execution retries.
    """

    normalized_approval_id = _required_text(
        approval_id,
        "approval_id",
        max_length=128,
    )
    normalized_member_id = _required_text(
        member_id,
        "member_id",
        max_length=128,
    )
    normalized_procedure_code = _required_text(
        procedure_code,
        "procedure_code",
        max_length=32,
    )
    normalized_provider_id = _required_text(
        provider_id,
        "provider_id",
        max_length=64,
    )
    normalized_justification = _required_text(
        justification,
        "justification",
        max_length=2000,
    )
    normalized_idempotency_key = _required_text(
        idempotency_key,
        "idempotency_key",
        max_length=256,
    )

    if not PROCEDURE_CODE_PATTERN.fullmatch(
        normalized_procedure_code
    ):
        raise ValueError(
            "procedure_code contains invalid characters"
        )

    if not PROVIDER_ID_PATTERN.fullmatch(
        normalized_provider_id
    ):
        raise ValueError(
            "provider_id contains invalid characters"
        )

    return {
        "success": True,
        "submission_mode": "SIMULATED",
        "submission_status": "SUBMITTED",
        "external_reference": _external_reference(
            normalized_idempotency_key
        ),
        "approval_id": normalized_approval_id,
        "member_id": normalized_member_id,
        "procedure_code": normalized_procedure_code,
        "provider_id": normalized_provider_id,
        "justification_received": bool(
            normalized_justification
        ),
        "idempotency_key": normalized_idempotency_key,
        "message": (
            "Simulated prior-authorization submission accepted. "
            "No real payer or healthcare system was contacted."
        ),
    }


@mcp.custom_route(
    "/health",
    methods=["GET"],
)
async def health(
    request: Request,
) -> Response:
    """Cloud Run health endpoint containing no private data."""

    _ = request

    return JSONResponse(
        {
            "status": "ok",
            "service": (
                "membercare-prior-authorization-mcp"
            ),
            "submission_mode": "SIMULATED",
        }
    )


# Cloud Run's managed reverse proxy controls the public Host header.
# Disabling the SDK's localhost-only DNS-rebinding check is the
# documented configuration for such a trusted reverse proxy. Cloud Run
# IAM remains the service authentication boundary.
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
)


# Streamable HTTP endpoint: /mcp
app = mcp.streamable_http_app(
    transport_security=transport_security,
)