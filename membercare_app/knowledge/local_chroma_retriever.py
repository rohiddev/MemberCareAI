from __future__ import annotations

from typing import Any

from membercare_app.knowledge.vector_store import semantic_search


def retrieve(
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Retrieve MemberCareAI enterprise knowledge from the
    local persistent Chroma vector store.

    This is an adapter around vector_store.semantic_search().

    It normalizes local Chroma results into the common
    knowledge retrieval contract used by MemberCareAI.

    Common result format:

        {
            "text": "...",
            "source": "...",
            "score": 0.82,
            "metadata": {...},
        }

    This allows callers to switch between:

        KNOWLEDGE_BACKEND=local
            -> Chroma

        KNOWLEDGE_BACKEND=vertex
            -> Vertex AI RAG Engine

    without changing agent or tool code.
    """

    normalized_query = query.strip()

    if not normalized_query:
        return []

    if top_k < 1:
        raise ValueError(
            "top_k must be at least 1"
        )

    results = semantic_search(
        normalized_query,
        top_k=top_k,
    )

    normalized_results: list[
        dict[str, Any]
    ] = []

    for result in results:
        metadata = (
            result.get("metadata")
            or {}
        )

        source = (
            metadata.get("source_path")
            or metadata.get("document_title")
            or metadata.get("document_id")
            or "local_chroma"
        )

        normalized_results.append(
            {
                "text": (
                    result.get("content")
                    or ""
                ),
                "source": source,
                "score": result.get(
                    "similarity"
                ),
                "metadata": {
                    **metadata,
                    "backend": "local",
                    "chunk_id": result.get(
                        "chunk_id"
                    ),
                    "distance": result.get(
                        "distance"
                    ),
                },
            }
        )

    return normalized_results