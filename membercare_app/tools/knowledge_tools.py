from membercare_app.knowledge.retriever import (
    retrieve_knowledge,
)


def search_plan_knowledge(
    query: str,
    top_k: int = 3,
) -> dict:
    """
    Search MemberCareAI enterprise plan/policy knowledge.

    The configured backend is selected by KNOWLEDGE_BACKEND:

      - local  -> ChromaDB
      - vertex -> Vertex AI RAG Engine

    This tool returns general enterprise knowledge only. It must not
    be used as the source of truth for member-specific benefits,
    deductible values, claim amounts, or member identity.
    """

    normalized_query = query.strip()

    if not normalized_query:
        return {
            "found": False,
            "results": [],
            "error": "query is required",
        }

    results = retrieve_knowledge(
        query=normalized_query,
        top_k=top_k,
    )

    if not results:
        return {
            "found": False,
            "results": [],
            "error": (
                "No relevant enterprise knowledge "
                "was found."
            ),
        }

    safe_results = []

    for result in results:
        metadata = (
            result.get("metadata")
            or {}
        )

        safe_results.append(
            {
                "chunk_id": metadata.get(
                    "chunk_id"
                ),
                "document_title": (
                    metadata.get("document_title")
                    or metadata.get("title")
                    or result.get("source")
                ),
                "section_title": metadata.get(
                    "section_title"
                ),
                "source": result.get(
                    "source"
                ),
                "content": result.get(
                    "text"
                ),
                "similarity": result.get(
                    "score"
                ),
                "backend": metadata.get(
                    "backend"
                ),
            }
        )

    return {
        "found": True,
        "result_count": len(
            safe_results
        ),
        "results": safe_results,
    }