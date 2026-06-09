#!/usr/bin/env python3
"""Copy corpus data (document_sources + documents with vectors) from one
Postgres instance to another, without re-embedding.

Usage::

    # Both URLs from .env (DEV_DATABASE_URL, SUPABASE_DIRECT_URL):
    uv run python scripts/copy_corpus_data.py

    # Explicit URLs (overrides .env):
    uv run python scripts/copy_corpus_data.py \\
        --source "postgresql+asyncpg://..." \\
        --target "postgresql+asyncpg://..."

    # Single corpus:
    uv run python scripts/copy_corpus_data.py --corpus "eu-ai-act"

    # Dry run — read source, print counts, write nothing:
    uv run python scripts/copy_corpus_data.py --dry-run

Environment variables (in .env)
-------------------------------
DEV_DATABASE_URL
    Source database (asyncpg DSN).  If not set, falls back to the
    app's ``POSTGRES_*`` settings.
SUPABASE_DIRECT_URL
    Target database (asyncpg DSN).  Required for non-dry-run copies.

Process
-------
1. Run ``migrate_db(target_url)`` — creates pgvector extension, tables,
   indexes, FK constraints (idempotent).
2. Read ``document_sources`` and ``documents`` from source (optionally
   filtered by ``--corpus``).
3. Delete any existing rows for the same ``corpus_id``(s) on target.
4. Insert ``document_sources`` first (FK parent).
5. Insert ``documents`` in batches with their vector embeddings, preserving
   original IDs.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, delete as sa_delete

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.db import create_db_sessionmaker, migrate_db
from backend.models import Document, DocumentSource


DEFAULT_BATCH_SIZE = 100


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Copy corpus data between Postgres instances without re-embedding"
    )

    default_source = settings.dev_database_url or settings.database_url
    parser.add_argument(
        "--source",
        default=default_source,
        help="Source database URL.  Default: $DEV_DATABASE_URL or POSTGRES_* vars.",
    )

    parser.add_argument(
        "--target",
        default=settings.supabase_direct_url,
        help="Target database URL.  Default: $SUPABASE_DIRECT_URL",
    )

    parser.add_argument(
        "--corpus",
        default=None,
        help="Copy only this corpus slug (corpus_id).  Omit to copy all corpora.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Documents per INSERT batch (default: {DEFAULT_BATCH_SIZE})",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read from source and report counts without writing to target.",
    )

    return parser.parse_args(argv)


async def copy_corpus_data(
    source_url: str,
    target_url: str,
    corpus_id: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """Copy corpus data from *source_url* to *target_url*.

    Returns
    -------
    (sources_count, documents_count, corpus_ids)
        Number of source file records, number of document chunks, and
        the list of affected corpus IDs.
    """
    source_sm = create_db_sessionmaker(source_url)

    # ── 1. Read from source ──────────────────────────────────────────
    async with source_sm() as session:
        src_sources_q = select(DocumentSource).order_by(
            DocumentSource.corpus_id, DocumentSource.filename
        )
        src_docs_q = select(Document).order_by(Document.id)
        if corpus_id:
            src_sources_q = src_sources_q.where(
                DocumentSource.corpus_id == corpus_id
            )
            src_docs_q = src_docs_q.where(Document.corpus_id == corpus_id)

        src_sources = (await session.execute(src_sources_q)).scalars().all()
        src_docs = (await session.execute(src_docs_q)).scalars().all()

    affected_corpus_ids = sorted({s.corpus_id for s in src_sources})
    print(f"Read {len(src_sources)} source file(s), {len(src_docs)} chunk(s)"
          f" from {len(affected_corpus_ids)} corpus/corpora: {affected_corpus_ids}")

    if dry_run:
        return len(src_sources), len(src_docs), affected_corpus_ids

    # ── 2. Migrate target schema (idempotent) ────────────────────────
    print("Migrating target schema...")
    await migrate_db(target_url)

    # ── 3. Write to target ───────────────────────────────────────────
    target_sm = create_db_sessionmaker(target_url)

    async with target_sm() as session:
        # Delete existing data for the affected corpus IDs
        for cid in affected_corpus_ids:
            await session.execute(
                sa_delete(Document).where(Document.corpus_id == cid)
            )
            await session.execute(
                sa_delete(DocumentSource).where(DocumentSource.corpus_id == cid)
            )
        await session.commit()
        print(f"Cleared existing data for {len(affected_corpus_ids)} corpus/corpora")

        # Insert document_sources first (FK target for documents)
        for src in src_sources:
            session.add(
                DocumentSource(
                    corpus_id=src.corpus_id,
                    filename=src.filename,
                    content_hash=src.content_hash,
                    updated_at=src.updated_at,
                )
            )
        await session.flush()
        print(f"Inserted {len(src_sources)} source file record(s)")

        # Insert documents in batches, preserving original IDs
        total = 0
        for i in range(0, len(src_docs), batch_size):
            batch = src_docs[i : i + batch_size]
            for doc in batch:
                session.add(
                    Document(
                        id=doc.id,
                        corpus_id=doc.corpus_id,
                        source_filename=doc.source_filename,
                        content=doc.content,
                        embedding=doc.embedding,
                        doc_metadata=doc.doc_metadata,
                    )
                )
            await session.commit()
            total += len(batch)
            print(f"  Inserted {total}/{len(src_docs)} document chunk(s)...")

    print(f"✅ Done — {len(src_sources)} source(s), {len(src_docs)} chunk(s) copied")
    return len(src_sources), len(src_docs), affected_corpus_ids


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.source:
        print(
            "ERROR: --source is required "
            "(set DEV_DATABASE_URL or POSTGRES_* in .env)",
            file=sys.stderr,
        )
        return 1
    if not args.dry_run and not args.target:
        print(
            "ERROR: --target is required (or set SUPABASE_DIRECT_URL in .env)",
            file=sys.stderr,
        )
        return 1

    await copy_corpus_data(
        source_url=args.source,
        target_url=args.target,
        corpus_id=args.corpus,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
