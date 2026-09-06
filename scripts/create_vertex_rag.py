from __future__ import annotations

import os

import agentplatform
from agentplatform import types
from google.genai import types as genai_types


PROJECT_ID = "membercare-ai"
LOCATION = "us-central1"

CORPUS_DISPLAY_NAME = "membercare-policy-corpus"

GCS_URIS = [
    "gs://membercare-ai-rag/knowledge/choice_plus_gold.md",
    "gs://membercare-ai-rag/knowledge/claims_guide.md",
]


def get_or_create_corpus(
    client: agentplatform.Client,
):
    """
    Reuse an existing RAG corpus when MEMBERCARE_RAG_CORPUS
    is provided.

    Otherwise create a new Vertex AI RAG corpus.
    """

    existing_corpus = os.getenv(
        "MEMBERCARE_RAG_CORPUS",
        "",
    ).strip()

    if existing_corpus:
        print()
        print("=" * 70)
        print("USING EXISTING RAG CORPUS")
        print("=" * 70)
        print(existing_corpus)

        return existing_corpus

    print()
    print("=" * 70)
    print("CREATING VERTEX AI RAG CORPUS")
    print("=" * 70)

    corpus = client.rag.create_corpus(
        rag_corpus=types.RagCorpus(
            display_name=CORPUS_DISPLAY_NAME,
            description=(
                "Synthetic MemberCareAI benefits, "
                "plan, and claims policy knowledge."
            ),
        )
    )

    print()
    print("=" * 70)
    print("CORPUS CREATED")
    print("=" * 70)
    print("NAME:")
    print(corpus.name)

    return corpus.name


def import_knowledge_files(
    client: agentplatform.Client,
    corpus_name: str,
) -> None:
    """
    Import MemberCareAI policy documents from GCS
    into the Vertex AI RAG corpus.
    """

    print()
    print("=" * 70)
    print("IMPORTING KNOWLEDGE FILES")
    print("=" * 70)

    for uri in GCS_URIS:
        print(uri)

    result = client.rag.import_files(
        name=corpus_name,
        import_config=types.ImportRagFilesConfig(
            gcs_source=genai_types.GcsSource(
                uris=GCS_URIS,
            ),
            rag_file_transformation_config=(
                types.RagFileTransformationConfig(
                    rag_file_chunking_config=(
                        types.RagFileChunkingConfig(
                            chunk_size=512,
                            chunk_overlap=100,
                        )
                    )
                )
            ),
        ),
    )

    print()
    print("=" * 70)
    print("IMPORT RESULT")
    print("=" * 70)
    print(result)


def main() -> None:
    print()
    print("=" * 70)
    print("MemberCareAI Vertex RAG Setup")
    print("=" * 70)
    print("PROJECT:", PROJECT_ID)
    print("LOCATION:", LOCATION)

    client = agentplatform.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    corpus_name = get_or_create_corpus(
        client,
    )

    import_knowledge_files(
        client,
        corpus_name,
    )

    print()
    print("=" * 70)
    print("RAG CONFIGURATION")
    print("=" * 70)

    print(
        "KNOWLEDGE_BACKEND=vertex"
    )

    print(
        f"MEMBERCARE_RAG_LOCATION={LOCATION}"
    )

    print(
        f"MEMBERCARE_RAG_CORPUS={corpus_name}"
    )


if __name__ == "__main__":
    main()