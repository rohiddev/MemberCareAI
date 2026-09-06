from pathlib import Path

from membercare_app.knowledge.chunker import (
    chunk_knowledge_directory,
)
from membercare_app.knowledge.vector_store import (
    reset_collection,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

KNOWLEDGE_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "knowledge"
)


def main():

    print()
    print(
        "MEMBERCAREAI KNOWLEDGE INDEXER"
    )

    print(
        "=" * 70
    )

    chunks = (
        chunk_knowledge_directory(
            KNOWLEDGE_DIRECTORY
        )
    )

    print(
        "Chunks discovered:",
        len(chunks),
    )

    collection = (
        reset_collection()
    )

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(chunks)}]"
        )

        print(
            "Document:",
            chunk.document_title,
        )

        print(
            "Section:",
            chunk.section_title,
        )

        print(
            "Chunk ID:",
            chunk.chunk_id,
        )

        # Generate real Vertex AI embedding.

        from membercare_app.knowledge.embeddings import (
            embed_document,
        )

        vector = embed_document(
            chunk.content
        )

        print(
            "Embedding dimensions:",
            len(vector),
        )

        collection.upsert(
            ids=[
                chunk.chunk_id
            ],
            embeddings=[
                vector
            ],
            documents=[
                chunk.content
            ],
            metadatas=[
                {
                    "document_id": (
                        chunk.document_id
                    ),
                    "document_title": (
                        chunk.document_title
                    ),
                    "section_title": (
                        chunk.section_title
                    ),
                    "source_path": (
                        chunk.source_path
                    ),
                }
            ],
        )

    print()
    print(
        "=" * 70
    )

    print(
        "INDEX COMPLETE"
    )

    print(
        "Collection:",
        collection.name,
    )

    print(
        "Stored chunks:",
        collection.count(),
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()