from typing import Any

from membercare_app.config.firestore import get_firestore_client
from membercare_app.context.request_context import get_member_id


def get_provider_network_status(
    provider_id: str,
) -> dict[str, Any]:
    """
    Retrieve network information for a provider.

    This capability returns administrative provider-network facts.

    It does NOT determine service coverage, medical necessity,
    or expected member cost.
    """

    if not provider_id:
        return {
            "found": False,
            "authorized": False,
            "error": "provider_id is required",
        }

    authenticated_member_id = get_member_id()

    if not authenticated_member_id:
        return {
            "found": False,
            "authorized": False,
            "error": "authenticated member context is missing",
        }

    db = get_firestore_client()

    # --------------------------------------------------------
    # Verify authenticated member exists
    # --------------------------------------------------------

    member_document = (
        db.collection("members")
        .document(authenticated_member_id)
        .get()
    )

    if not member_document.exists:
        return {
            "found": False,
            "authorized": False,
            "error": "authenticated member not found",
        }

    # --------------------------------------------------------
    # Retrieve provider
    # --------------------------------------------------------

    provider_document = (
        db.collection("providers")
        .document(provider_id)
        .get()
    )

    if not provider_document.exists:
        return {
            "found": False,
            "authorized": True,
            "provider_id": provider_id,
            "error": "provider not found",
        }

    provider = provider_document.to_dict()

    return {
        "found": True,
        "authorized": True,
        "provider": provider,
    }