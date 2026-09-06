from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from membercare_app.config.firestore import get_firestore_client


SESSIONS_COLLECTION = "sessions"
MESSAGES_SUBCOLLECTION = "messages"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_session(
    session_id: str,
    user_id: str,
    member_id: str,
) -> None:
    """
    Create the session document if it does not already exist.

    Existing session metadata is preserved, while updated_at
    is refreshed.
    """

    db = get_firestore_client()

    session_ref = (
        db.collection(SESSIONS_COLLECTION)
        .document(session_id)
    )

    snapshot = session_ref.get()

    now = _utc_now()

    if snapshot.exists:
        session_ref.set(
            {
                "updated_at": now,
            },
            merge=True,
        )

        return

    session_ref.set(
        {
            "session_id": session_id,
            "user_id": user_id,
            "member_id": member_id,
            "created_at": now,
            "updated_at": now,
        }
    )


def add_message(
    session_id: str,
    role: str,
    content: str,
) -> str:
    """
    Persist one conversation message in Firestore.

    Returns the generated message ID.
    """

    if role not in {
        "user",
        "assistant",
    }:
        raise ValueError(
            "role must be 'user' or 'assistant'"
        )

    if not content:
        raise ValueError(
            "content must not be empty"
        )

    db = get_firestore_client()

    message_id = str(
        uuid4()
    )

    message_ref = (
        db.collection(SESSIONS_COLLECTION)
        .document(session_id)
        .collection(MESSAGES_SUBCOLLECTION)
        .document(message_id)
    )

    message_ref.set(
        {
            "message_id": message_id,
            "role": role,
            "content": content,
            "timestamp": _utc_now(),
        }
    )

    (
        db.collection(SESSIONS_COLLECTION)
        .document(session_id)
        .set(
            {
                "updated_at": _utc_now(),
            },
            merge=True,
        )
    )

    return message_id


def get_recent_messages(
    session_id: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    Retrieve the most recent conversation messages.

    Results are returned oldest-to-newest so they can be
    inserted naturally into an LLM prompt.
    """

    db = get_firestore_client()

    query = (
        db.collection(SESSIONS_COLLECTION)
        .document(session_id)
        .collection(MESSAGES_SUBCOLLECTION)
        .order_by(
            "timestamp",
            direction="DESCENDING",
        )
        .limit(limit)
    )

    documents = list(
        query.stream()
    )

    messages = [
        document.to_dict()
        for document in documents
    ]

    messages.reverse()

    return messages