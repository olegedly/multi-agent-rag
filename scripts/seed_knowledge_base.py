#!/usr/bin/env python3
"""Idempotent knowledge-base seeding script.

Computes SHA-256 of each source file, compares against the
``document_sources`` table, and applies a diff:
  - Insert new files
  - Update changed files
  - Delete removed files
  - Skip unchanged files

Usage::

    uv run python scripts/seed_knowledge_base.py --corpus <slug>
    uv run python scripts/seed_knowledge_base.py --all
"""

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select, delete as sa_delete

# Ensure ``backend/`` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.corpus_config import CorporaConfig
from backend.db import create_db_sessionmaker, migrate_db
from backend.embeddings.factory import create_embedding_client
from backend.models import Document, DocumentSource

# ── Helpers ──────────────────────────────────────────────────────────────────


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _read_files(corpus_config: CorporaConfig, corpus) -> list[tuple[str, str]]:
    """Read all files matching the corpus's doc glob and return ``(filename, content)`` pairs."""
    files = corpus_config.resolve_document_glob(corpus)
    result: list[tuple[str, str]] = []
    for fpath in files:
        content = fpath.read_text(encoding="utf-8")
        result.append((str(fpath), content))
    return result


def _get_key(filename: str, root: Path) -> str:
    """Return the relative path for use as a stable file key.

    Produces paths like ``corpora/mcp-spec/Tools.md`` regardless of
    absolute path differences.
    """
    try:
        return str(Path(filename).relative_to(root))
    except ValueError:
        return filename


# ── Diff logic ────────────────────────────────────────────────────────────────


def compute_diff(
    files: list[tuple[str, str]],
    source_store: dict[str, str],
    root: Path,
) -> dict[str, list]:
    """Compare source files against stored hashes and return a diff plan.

    *root* is the project root used by :func:`_get_key` to produce relative paths.
    *source_store* maps ``filename → content_hash`` for the active corpus.
    """
    plan: dict[str, list] = {"insert": [], "update": [], "delete": [], "skip": []}

    # Check each disk file against stored hash
    for fname, content in files:
        key = _get_key(fname, root)
        disk_hash = _sha256(content)
        stored_hash = source_store.get(key)
        if stored_hash is None:
            plan["insert"].append((key, fname, content))
        elif stored_hash != disk_hash:
            plan["update"].append((key, fname, content))
        else:
            plan["skip"].append((key, disk_hash))

    # Find files in store that no longer exist on disk
    disk_keys = {_get_key(fname, root) for fname, _content in files}
    for fname in source_store:
        if fname not in disk_keys:
            plan["delete"].append((fname,))

    return plan


# ── Main ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Idempotent knowledge-base seeding script"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--corpus", type=str, help="Corpus slug to seed")
    group.add_argument("--all", action="store_true", help="Seed all configured corpora")
    return parser.parse_args(argv)


async def seed_corpus(
    corpus_config: CorporaConfig,
    corpus,
    embedding_client,
    sessionmaker,
) -> int:
    """Seed a single corpus. Returns number of chunks inserted."""
    corpus_id = corpus.id
    slug = corpus.slug

    print(f"\n📚 Seeding corpus: {corpus.name} ({slug})")

    # ── Discover files ────────────────────────────────────────────────
    files = _read_files(corpus_config, corpus)
    if not files:
        print(f"  → No files matched {corpus.documents}, nothing to seed")
        return 0
    print(f"  → Found {len(files)} source file(s)")

    # ── Load existing hashes from DB ──────────────────────────────────
    async with sessionmaker() as session:
        result = await session.execute(
            select(DocumentSource).where(DocumentSource.corpus_id == corpus_id)
        )
        source_store: dict[str, str] = {}
        for row in result.scalars():
            source_store[row.filename] = row.content_hash

    # ── Compute diff ──────────────────────────────────────────────────
    root = corpus_config.project_root  # relative path anchor
    plan = compute_diff(files, source_store, root)
    print(f"  → {len(plan['insert'])} insert(s), {len(plan['update'])} update(s), "
          f"{len(plan['delete'])} delete(s), {len(plan['skip'])} skip(s)")

    chunker = corpus_config.get_chunker(slug)
    assert chunker is not None
    total_chunks = 0

    # ── Process (insert + update) ─────────────────────────────────────
    to_process = plan["insert"] + plan["update"]
    for key, _fname, content in to_process:
        # NOTE: source_url is intentionally omitted — the knowledge base contains
        # local files that have no web-accessible URL.  The LLM must not be given
        # an empty string to avoid URL hallucination in citations.
        chunks = chunker.chunk(content, {"title": key})
        texts = [c.content for c in chunks]
        embeddings = await embedding_client.embed_texts(texts)

        async with sessionmaker() as session:
            # Delete old chunks for this file
            await session.execute(
                sa_delete(Document).where(
                    Document.corpus_id == corpus_id,
                    Document.source_filename == key,
                )
            )

            # Upsert document_source FIRST (FK target for documents)
            existing = await session.get(DocumentSource, (corpus_id, key))
            if existing:
                existing.content_hash = _sha256(content)
            else:
                session.add(DocumentSource(
                    corpus_id=corpus_id,
                    filename=key,
                    content_hash=_sha256(content),
                ))
            await session.flush()

            # Insert new chunks (FK references document_source now present)
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                doc = Document(
                    corpus_id=corpus_id,
                    source_filename=key,
                    content=chunk.content,
                    embedding=embedding,
                    doc_metadata=chunk.metadata,
                )
                session.add(doc)

            await session.commit()

        total_chunks += len(chunks)
        print(f"    ● {key}: {len(chunks)} chunks, {len(embeddings)} embeddings")

    # ── Process (delete) ─────────────────────────────────────────────
    for (del_key,) in plan["delete"]:
        async with sessionmaker() as session:
            await session.execute(
                sa_delete(Document).where(
                    Document.corpus_id == corpus_id,
                    Document.source_filename == del_key,
                )
            )
            await session.execute(
                sa_delete(DocumentSource).where(
                    DocumentSource.corpus_id == corpus_id,
                    DocumentSource.filename == del_key,
                )
            )
            await session.commit()
        print(f"    ✗ {del_key}: removed")

    print(f"  ✅ {total_chunks} chunks written to DB for {slug}")
    return total_chunks


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    corpus_config = CorporaConfig()

    if not corpus_config.list():
        print("No corpora configured in corpora.yaml")
        return 0

    if args.all:
        to_seed = corpus_config.list()
    else:
        matched = corpus_config.get(args.corpus)
        if matched is None:
            print(f"Corpus '{args.corpus}' not found in corpora.yaml")
            return 1
        to_seed = [matched]

    # ── Migrate database ────────────────────────────────────────────
    settings = get_settings()
    await migrate_db(settings.database_url)

    sessionmaker = create_db_sessionmaker(settings.database_url)
    embedding_client = create_embedding_client()

    total = 0
    for corpus in to_seed:
        total += await seed_corpus(corpus_config, corpus, embedding_client, sessionmaker)

    print(f"\n📊 Total: {total} chunks across {len(to_seed)} corpus/corpora")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
