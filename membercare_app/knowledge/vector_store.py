from pathlib import Path


from membercare_app.knowledge.embeddings import (
    embed_document,
    embed_query,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

CHROMA_PATH = (
    PROJECT_ROOT
    / "data"
    / "chroma"
)

COLLECTION_NAME = (
    "membercare_knowledge"
)


def get_chroma_client():
    """
    Return the persistent local Chroma client.
    """

    import chromadb

    return chromadb.PersistentClient(
        path=str(
            CHROMA_PATH
        )
    )


def get_collection():
    """
    Return the MemberCareAI knowledge collection.

    We provide embeddings ourselves using Vertex AI,
    so Chroma does not need its own embedding function.
    """

    client = get_chroma_client()

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
        },
    )


def reset_collection():
    """
    Delete and recreate the development collection.

    Useful when rebuilding the local index.
    """

    client = get_chroma_client()

    try:
        client.delete_collection(
            COLLECTION_NAME
        )
    except Exception:
        pass

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
        },
    )


def add_chunk(
    *,
    chunk_id: str,
    document_id: str,
    document_title: str,
    section_title: str,
    content: str,
    source_path: str,
) -> None:
    """
    Embed and persist one enterprise knowledge chunk.
    """

    vector = embed_document(
        content
    )

    collection = get_collection()

    collection.upsert(
        ids=[
            chunk_id
        ],
        embeddings=[
            vector
        ],
        documents=[
            content
        ],
        metadatas=[
            {
                "document_id": document_id,
                "document_title": (
                    document_title
                ),
                "section_title": (
                    section_title
                ),
                "source_path": source_path,
            }
        ],
    )


def semantic_search(
    query: str,
    *,
    top_k: int = 3,
) -> list[dict]:
    """
    Search enterprise knowledge using a real query embedding.
    """

    if not query.strip():
        return []

    collection = get_collection()

    if collection.count() == 0:
        return []

    query_vector = embed_query(
        query
    )

    results = collection.query(
        query_embeddings=[
            query_vector
        ],
        n_results=top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    output = []

    ids = (
        results.get("ids", [[]])[0]
    )

    documents = (
        results.get(
            "documents",
            [[]],
        )[0]
    )

    metadatas = (
        results.get(
            "metadatas",
            [[]],
        )[0]
    )

    distances = (
        results.get(
            "distances",
            [[]],
        )[0]
    )

    for (
        chunk_id,
        document,
        metadata,
        distance,
    ) in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):

        output.append(
            {
                "chunk_id": chunk_id,
                "content": document,
                "metadata": metadata,
                "distance": distance,
                # cosine distance:
                # smaller = more similar
                "similarity": (
                    round(
                        1.0 - distance,
                        4,
                    )
                ),
            }
        )

    return output