from __future__ import annotations

import os
from typing import Any

from membercare_app.knowledge import local_chroma_retriever
from membercare_app.knowledge import vertex_rag_retriever


SUPPORTED_BACKENDS = {"local", "vertex"}


def get_knowledge_backend() -> str:
    """
    Return the configured knowledge backend.

    Supported values:
      - local  -> local Chroma vector database
      - vertex -> Vertex AI RAG Engine

    Default:
      local
    """

    backend = os.getenv(
        "KNOWLEDGE_BACKEND",
        "local",
    ).strip().lower()

    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            "Unsupported KNOWLEDGE_BACKEND="
            f"{backend!r}. "
            f"Expected one of: {sorted(SUPPORTED_BACKENDS)}"
        )

    return backend


def retrieve_knowledge(
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Retrieve enterprise knowledge using the configured backend.

    This is the stable retrieval interface used by MemberCareAI.

    The Benefits Agent / Tool Gateway should not need to know whether
    the actual implementation is:

        local -> Chroma
        vertex -> Vertex AI RAG Engine

    Args:
        query:
            Natural-language knowledge query.

        top_k:
            Maximum number of retrieved chunks.

    Returns:
        A normalized list of dictionaries.

        Example:

        [
            {
                "text": "...",
                "source": "choice_plus_gold.md",
                "score": 0.81,
                "metadata": {...},
            }
        ]
    """

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query must not be empty")

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    backend = get_knowledge_backend()

    if backend == "local":
        return local_chroma_retriever.retrieve(
            query=normalized_query,
            top_k=top_k,
        )

    if backend == "vertex":
        return vertex_rag_retriever.retrieve(
            query=normalized_query,
            top_k=top_k,
        )

    # Defensive fallback. get_knowledge_backend() already validates.
    raise RuntimeError(
        f"Knowledge backend routing failed for backend={backend!r}"
    )