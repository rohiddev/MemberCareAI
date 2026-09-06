from __future__ import annotations

import os

from membercare_app.knowledge.retriever import retrieve_knowledge


def main() -> None:
    backend = os.getenv(
        "KNOWLEDGE_BACKEND",
        "local",
    )

    query = "What is a deductible?"

    print()
    print("=" * 70)
    print("MemberCareAI RAG Retrieval Test")
    print("=" * 70)
    print("BACKEND:", backend)
    print("QUERY:", query)

    results = retrieve_knowledge(
        query=query,
        top_k=3,
    )

    print()
    print("RESULT COUNT:", len(results))

    for index, item in enumerate(
        results,
        start=1,
    ):
        print()
        print("=" * 70)
        print(f"RESULT {index}")
        print("=" * 70)

        print(
            "SOURCE:",
            item.get("source"),
        )

        print(
            "SCORE:",
            item.get("score"),
        )

        print(
            "METADATA:",
            item.get("metadata"),
        )

        print()
        print("TEXT:")
        print(
            item.get("text")
        )


if __name__ == "__main__":
    main()