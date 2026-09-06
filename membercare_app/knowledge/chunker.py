from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    document_title: str
    section_title: str
    content: str
    source_path: str


def _document_title(
    content: str,
    fallback: str,
) -> str:
    """
    Use the first markdown H1 as the document title.
    """

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("# "):
            return stripped[2:].strip()

    return fallback


def chunk_markdown_file(
    path: Path,
) -> list[KnowledgeChunk]:
    """
    Split a Markdown document primarily by H2 sections.

    Example:

        # Plan Guide

        ## Deductible
        ...

        ## Coinsurance
        ...

    becomes separate searchable chunks.
    """

    content = path.read_text(
        encoding="utf-8"
    )

    document_id = path.stem

    title = _document_title(
        content,
        fallback=(
            path.stem
            .replace("_", " ")
            .title()
        ),
    )

    chunks: list[KnowledgeChunk] = []

    current_section = "Overview"
    current_lines: list[str] = []

    def flush_chunk() -> None:
        if not current_lines:
            return

        chunk_text = "\n".join(
            current_lines
        ).strip()

        if not chunk_text:
            return

        section_slug = (
            current_section
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
        )

        chunk_number = len(chunks) + 1

        chunk_id = (
            f"{document_id}-"
            f"{chunk_number:03d}-"
            f"{section_slug}"
        )

        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                document_title=title,
                section_title=current_section,
                content=chunk_text,
                source_path=str(path),
            )
        )

    for line in content.splitlines():

        stripped = line.strip()

        if stripped.startswith("## "):

            flush_chunk()

            current_section = (
                stripped[3:].strip()
            )

            current_lines = []

            continue

        # Ignore the top-level title because it is already
        # stored as metadata.

        if stripped.startswith("# "):
            continue

        current_lines.append(
            line
        )

    flush_chunk()

    return chunks


def chunk_knowledge_directory(
    directory: Path,
) -> list[KnowledgeChunk]:
    """
    Chunk every Markdown file in a knowledge directory.
    """

    chunks: list[KnowledgeChunk] = []

    if not directory.exists():
        return chunks

    for path in sorted(
        directory.glob("*.md")
    ):
        chunks.extend(
            chunk_markdown_file(
                path
            )
        )

    return chunks