import json
import logging
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("membercareai")

if not logger.handlers:
    handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

logger.setLevel(logging.INFO)


def emit_event(
    event_type: str,
    **attributes: Any,
) -> None:
    """
    Emit one structured MemberCareAI observability event.

    Do not put PHI, prompts, or full model responses here.

    Safe examples:
    - request_id
    - agent_name
    - tool_name
    - success
    - latency_ms
    - gateway_status
    """

    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "service": "MemberCareAI",
        "event_type": event_type,
        **attributes,
    }

    logger.info(
        json.dumps(
            event,
            default=str,
        )
    )