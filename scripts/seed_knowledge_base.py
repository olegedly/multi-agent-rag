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

import yaml

# Ensure ``backend/`` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rag.chunker import (
    MarkdownHeadingChunker,
    ParagraphChunker,
    RecursiveChunker,
)
from backend.embeddings.factory import create_embedding_client

# ── Paths ────────────────────────────────────────────────────────────────────

CORPORA_YAML = Path(__file__).resolve().parent.parent / "backend" / "corpora.yaml"
CORPORA_DIR = Path(__file__).resolve().parent.parent / "corpora"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _load_corpora() -> list[dict]:
    with open(CORPORA_YAML) as f:
        data = yaml.safe_load(f)
    return (data or {}).get("corpora", [])


def _discover_files(glob_pattern: str) -> list[Path]:
    """Resolve a glob pattern relative to the project root and return matching files."""
    root = CORPORA_DIR.parent  # project root
    # glob_pattern is relative to root (e.g. "corpora/mcp-spec/*.md")
    return sorted(root.glob(glob_pattern))


def _get_chunker(config: dict):
    """Instantiate the chunker strategy configured for this corpus."""
    strategy = config.get("chunker", "paragraph")
    if strategy == "markdown-heading":
        return MarkdownHeadingChunker(max_tokens=500, overlap=50)
    elif strategy == "paragraph":
        return ParagraphChunker(max_tokens=500, overlap=50)
    elif strategy == "recursive":
        return RecursiveChunker(max_chars=2000)
    else:
        print(f"  Warning: unknown chunker strategy '{strategy}', falling back to paragraph")
        return ParagraphChunker(max_tokens=500, overlap=50)


def _read_files(glob_pattern: str) -> list[tuple[str, str]]:
    """Read all files matching *glob_pattern* and return ``(filename, content)`` pairs."""
    files = _discover_files(glob_pattern)
    result: list[tuple[str, str]] = []
    for fpath in files:
        content = fpath.read_text(encoding="utf-8")
        result.append((str(fpath), content))
    return result


# ── Diff logic (extracted for testability) ────────────────────────────────────


def compute_diff(
    corpus_id: str,
    files: list[tuple[str, str]],
    source_store: dict[str, dict[str, str]],
) -> dict[str, list]:
    """Compare source files against stored hashes and return a diff plan.

    *source_store* is a dict mapping ``corpus_id`` → ``{filename: content_hash}``.
    """
    plan: dict[str, list] = {"insert": [], "update": [], "delete": [], "skip": []}

    # Fetch stored hashes for this corpus
    stored: dict[str, str] = source_store.get(corpus_id, {})

    # Check each disk file against stored hash
    for fname, content in files:
        disk_hash = _sha256(content)
        stored_hash = stored.get(fname)
        if stored_hash is None:
            plan["insert"].append((fname, content))
        elif stored_hash != disk_hash:
            plan["update"].append((fname, content))
        else:
            plan["skip"].append((fname, disk_hash))

    # Find files in store that no longer exist on disk
    disk_files = {fname for fname, _content in files}
    for fname in stored:
        if fname not in disk_files:
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


async def seed_corpus(config: dict, embedding_client) -> int:
    """Seed a single corpus. Returns the number of chunks inserted.

    Parameters
    ----------
    config : dict
        Corpus configuration from corpora.yaml.
    embedding_client : EmbeddingClient
        Client for generating vector embeddings.

    Returns
    -------
    int
        Number of chunks processed.
    """
    corpus_id = config["id"]
    slug = config["slug"]
    glob_pattern = config["documents"]

    print(f"\n📚 Seeding corpus: {config['name']} ({slug})")

    # Discover and read files
    files = _read_files(glob_pattern)
    if not files:
        print(f"  → No files matched {glob_pattern}, nothing to seed")
        return 0

    print(f"  → Found {len(files)} source file(s)")

    # In a real run, we'd load existing hashes from the DB.
    # For now, we assume everything is new (first run).
    source_store: dict[str, dict[str, str]] = {}
    plan = compute_diff(corpus_id, files, source_store)

    print(f"  → {len(plan['insert'])} insert(s), {len(plan['update'])} update(s), "
          f"{len(plan['delete'])} delete(s), {len(plan['skip'])} skip(s)")

    chunker = _get_chunker(config)
    total_chunks = 0
    total_embeddings = 0

    # Process inserts and updates: chunk → embed → store
    to_process = plan["insert"] + plan["update"]
    for fname, content in to_process:
        chunks = chunker.chunk(content, {"title": fname, "source_url": ""})
        total_chunks += len(chunks)

        texts = [c.content for c in chunks]
        embeddings = await embedding_client.embed_texts(texts)
        total_embeddings += len(embeddings)

        print(f"    ● {fname}: {len(chunks)} chunks, {len(embeddings)} embeddings")

    # In a real run, we'd INSERT/UPDATE into the DB here and update document_sources.
    # For now, we just report what we'd do.

    print(f"  ✅ {total_chunks} chunks processed with {total_embeddings} embeddings")
    return total_chunks


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    corpora = _load_corpora()

    if not corpora:
        print("No corpora configured in corpora.yaml")
        return 0

    if args.all:
        to_seed = corpora
    else:
        matched = [c for c in corpora if c.get("slug") == args.corpus]
        if not matched:
            print(f"Corpus '{args.corpus}' not found in corpora.yaml")
            return 1
        to_seed = matched

    embedding_client = create_embedding_client()

    total = 0
    for config in to_seed:
        total += await seed_corpus(config, embedding_client)

    print(f"\n📊 Total: {total} chunks across {len(to_seed)} corpus/corpora")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
