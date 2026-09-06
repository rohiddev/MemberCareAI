from google.cloud import firestore


PROJECT_ID = "membercare-ai"
DATABASE_ID = "membercare"


def get_firestore_client():
    """
    Return the Firestore client used by MemberCareAI.

    Project:
        membercare-ai

    Database:
        membercare

    Local authentication uses Application Default Credentials.
    In GCP, the runtime service account will provide credentials.
    """

    return firestore.Client(
        project=PROJECT_ID,
        database=DATABASE_ID,
    )