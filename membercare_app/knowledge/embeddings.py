from google import genai
from google.genai import types


PROJECT_ID = "membercare-ai"
LOCATION = "us-central1"

MODEL_NAME = "gemini-embedding-001"

EMBEDDING_DIMENSION = 768


client = genai.Client(
    enterprise=True,
    project=PROJECT_ID,
    location=LOCATION,
    http_options=types.HttpOptions(
        api_version="v1"
    ),
)


def _extract_vector(
    response,
) -> list[float]:
    """
    Extract the first embedding vector from the
    Google Gen AI SDK response.
    """

    if not response.embeddings:
        raise RuntimeError(
            "Embedding API returned no embeddings"
        )

    return list(
        response.embeddings[0].values
    )


def embed_document(
    text: str,
) -> list[float]:
    """
    Generate an embedding for an enterprise
    knowledge document or chunk.
    """

    if not text.strip():
        raise ValueError(
            "Document text cannot be empty"
        )

    response = client.models.embed_content(
        model=MODEL_NAME,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=(
                EMBEDDING_DIMENSION
            ),
        ),
    )

    return _extract_vector(
        response
    )


def embed_query(
    text: str,
) -> list[float]:
    """
    Generate an embedding for a semantic
    retrieval query.
    """

    if not text.strip():
        raise ValueError(
            "Query text cannot be empty"
        )

    response = client.models.embed_content(
        model=MODEL_NAME,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=(
                EMBEDDING_DIMENSION
            ),
        ),
    )

    return _extract_vector(
        response
    )