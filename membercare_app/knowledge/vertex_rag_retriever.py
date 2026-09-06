from __future__ import annotations

import os
from typing import Any

import agentplatform

from agentplatform import types as agentplatform_types
from google.genai import types as genai_types


DEFAULT_PROJECT_ID = "membercare-ai"
DEFAULT_RAG_LOCATION = "us-central1"


def _get_project_id() -> str:
    return os.getenv(
        "GOOGLE_CLOUD_PROJECT",
        DEFAULT_PROJECT_ID,
    )


def _get_rag_location() -> str:
    return os.getenv(
        "MEMBERCARE_RAG_LOCATION",
        DEFAULT_RAG_LOCATION,
    )


def _get_rag_corpus() -> str:
    corpus = os.getenv(
        "MEMBERCARE_RAG_CORPUS",
        "",
    ).strip()

    if not corpus:
        raise RuntimeError(
            "MEMBERCARE_RAG_CORPUS is required when "
            "KNOWLEDGE_BACKEND=vertex. "
            "Expected a resource name similar to: "
            "projects/422936875002/locations/us-central1/"
            "ragCorpora/<CORPUS_ID>"
        )

    return corpus


def _create_client() -> agentplatform.Client:
    return agentplatform.Client(
        project=_get_project_id(),
        location=_get_rag_location(),
    )


def _extract_contexts(
    response: Any,
) -> list[Any]:
    """
    Vertex RAG SDK response structures can vary slightly across SDK
    releases.

    Keep that SDK-specific behavior isolated here rather than leaking
    it into the rest of MemberCareAI.
    """

    outer_contexts = getattr(
        response,
        "contexts",
        None,
    )

    if outer_contexts is None:
        return []

    nested_contexts = getattr(
        outer_contexts,
        "contexts",
        None,
    )

    if nested_contexts is not None:
        return list(nested_contexts)

    if isinstance(outer_contexts, (list, tuple)):
        return list(outer_contexts)

    return []


def _get_attribute(
    obj: Any,
    *names: str,
    default: Any = None,
) -> Any:
    """
    Safely retrieve an attribute or dictionary value across small SDK
    response-shape differences.
    """

    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(
                obj,
                name,
                None,
            )

        if value is not None:
            return value

    return default


def _normalize_context(
    context: Any,
) -> dict[str, Any]:
    text = _get_attribute(
        context,
        "text",
        "content",
        default="",
    )

    source = _get_attribute(
        context,
        "source_uri",
        "sourceUri",
        "source",
        default="vertex_rag",
    )

    score = _get_attribute(
        context,
        "score",
        "distance",
        default=None,
    )

    metadata = {
        "backend": "vertex",
    }

    raw_metadata = _get_attribute(
        context,
        "metadata",
        default=None,
    )

    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)

    title = _get_attribute(
        context,
        "title",
        "display_name",
        "displayName",
        default=None,
    )

    if title:
        metadata["title"] = title

    return {
        "text": str(text or ""),
        "source": str(source or "vertex_rag"),
        "score": score,
        "metadata": metadata,
    }


def retrieve(
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Retrieve enterprise policy/plan knowledge using Vertex AI
    RAG Engine.

    Firestore remains the authoritative store for member-specific
    structured facts.

    This backend should only be used for knowledge such as:
      - plan policy language
      - deductible definitions
      - coinsurance explanations
      - claims guidance
      - administrative plan documentation
    """

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query must not be empty")

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    client = _create_client()

    rag_corpus = _get_rag_corpus()

    response = client.rag.retrieve_contexts(
        vertex_rag_store=genai_types.VertexRagStore(
            rag_resources=[
                genai_types.VertexRagStoreRagResource(
                    rag_corpus=rag_corpus,
                )
            ]
        ),
        query=agentplatform_types.RagQuery(
            text=normalized_query,
            rag_retrieval_config=genai_types.RagRetrievalConfig(
                top_k=top_k,
            ),
        ),
    )

    contexts = _extract_contexts(
        response,
    )

    return [
        _normalize_context(context)
        for context in contexts
        if _get_attribute(
            context,
            "text",
            "content",
            default="",
        )
    ]