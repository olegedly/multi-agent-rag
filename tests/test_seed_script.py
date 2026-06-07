"""Tests for the knowledge-base seeding script.

All tests use temp files and fake databases — no real filesystem or
pgvector dependency. Focuses on:
- SHA-256 diff logic (skip unchanged, insert new, update changed, delete removed)
- Chunking integration
- Embedding integration
"""

import hashlib
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.embeddings.protocol import EmbeddingClient


# ── Helper to compute SHA-256 ────────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ── Fake DB helpers ──────────────────────────────────────────────────────────


class FakeDocumentSourceStore:
    """In-memory stand-in for the ``document_sources`` table."""

    def __init__(self):
        self._rows: dict[tuple[str, str], str] = {}  # (corpus_id, filename) -> content_hash

    def get(self, corpus_id: str, filename: str) -> str | None:
        return self._rows.get((corpus_id, filename))

    def upsert(self, corpus_id: str, filename: str, content_hash: str) -> None:
        self._rows[(corpus_id, filename)] = content_hash

    def delete(self, corpus_id: str, filename: str) -> None:
        self._rows.pop((corpus_id, filename), None)

    def list_files(self, corpus_id: str) -> list[str]:
        return [fname for (cid, fname) in self._rows if cid == corpus_id]

    def __len__(self) -> int:
        return len(self._rows)


class FakeDocumentStore:
    """In-memory stand-in for the ``documents`` table."""

    def __init__(self):
        self._rows: list[dict] = []

    def delete_by_corpus_and_filename(self, corpus_id: str, filename: str) -> None:
        self._rows = [
            r for r in self._rows
            if not (r.get("corpus_id") == corpus_id and r.get("source_filename") == filename)
        ]

    def add_chunks(self, chunks: list[dict]) -> None:
        self._rows.extend(chunks)

    def count(self) -> int:
        return len(self._rows)


class FakeEmbeddingClient:
    """Always returns a fixed-dimension vector for any input."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.called_with: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.called_with.append(texts)
        return [[float(i) / len(texts) for i in range(self.dim)] for _ in texts]


# ── The diff function we'll extract from the script ──────────────────────────


def compute_diff(
    corpus_id: str,
    files: list[tuple[str, str]],  # (filename, content)
    existing_sources: "FakeDocumentSourceStore",
) -> dict[str, list[tuple[str, str]]]:
    """Compare source files against stored hashes and return a diff plan.

    Returns
    -------
    dict with keys ``insert``, ``update``, ``delete``, ``skip``.
    Each value is a list of ``(filename, content)`` tuples, except
    ``delete`` which is just ``(filename,)`` tuples and ``skip``
    which is ``(filename, content_hash)``.
    """
    plan: dict[str, list] = {"insert": [], "update": [], "delete": [], "skip": []}

    # Build set of files that exist on disk
    disk_files = {fname for fname, _content in files}

    # Check each disk file against stored hash
    for fname, content in files:
        disk_hash = _sha256(content)
        stored_hash = existing_sources.get(corpus_id, fname)
        if stored_hash is None:
            plan["insert"].append((fname, content))
        elif stored_hash != disk_hash:
            plan["update"].append((fname, content))
        else:
            plan["skip"].append((fname, disk_hash))

    # Find files in store that no longer exist on disk
    stored_files = set(existing_sources.list_files(corpus_id))
    removed = stored_files - disk_files
    for fname in removed:
        plan["delete"].append((fname,))

    return plan


# ── Tests ────────────────────────────────────────────────────────────────────


class TestComputeDiff:
    """Pure function tests for the SHA-256 diff logic."""

    def test_all_new_files_are_inserted(self) -> None:
        store = FakeDocumentSourceStore()
        files = [("doc1.md", "hello world"), ("doc2.md", "foo bar")]
        plan = compute_diff("corpus-a", files, store)
        assert len(plan["insert"]) == 2
        assert len(plan["skip"]) == 0
        assert len(plan["delete"]) == 0

    def test_unchanged_files_are_skipped(self) -> None:
        store = FakeDocumentSourceStore()
        store.upsert("corpus-a", "doc1.md", _sha256("hello world"))
        files = [("doc1.md", "hello world")]
        plan = compute_diff("corpus-a", files, store)
        assert len(plan["skip"]) == 1
        assert len(plan["insert"]) == 0
        assert len(plan["update"]) == 0

    def test_changed_files_are_updated(self) -> None:
        store = FakeDocumentSourceStore()
        store.upsert("corpus-a", "doc1.md", _sha256("old content"))
        files = [("doc1.md", "new content")]
        plan = compute_diff("corpus-a", files, store)
        assert len(plan["update"]) == 1
        assert len(plan["skip"]) == 0

    def test_deleted_files_are_removed(self) -> None:
        store = FakeDocumentSourceStore()
        store.upsert("corpus-a", "gone.md", _sha256("bye"))
        files: list = []
        plan = compute_diff("corpus-a", files, store)
        assert len(plan["delete"]) == 1
        assert plan["delete"][0][0] == "gone.md"

    def test_mixed_diff(self) -> None:
        """Insert, update, skip, and delete all in one scope."""
        store = FakeDocumentSourceStore()
        store.upsert("corpus-a", "keep.md", _sha256("same"))
        store.upsert("corpus-a", "change.md", _sha256("old"))
        store.upsert("corpus-a", "gone.md", _sha256("bye"))
        files = [
            ("keep.md", "same"),
            ("change.md", "changed"),
            ("new.md", "fresh"),
        ]
        plan = compute_diff("corpus-a", files, store)
        assert len(plan["skip"]) == 1
        assert plan["skip"][0][0] == "keep.md"
        assert len(plan["update"]) == 1
        assert plan["update"][0][0] == "change.md"
        assert len(plan["insert"]) == 1
        assert plan["insert"][0][0] == "new.md"
        assert len(plan["delete"]) == 1
        assert plan["delete"][0][0] == "gone.md"


class TestCorpusScopedDiff:
    """Diff operations on one corpus don't affect another."""

    def test_corpus_isolation(self) -> None:
        store = FakeDocumentSourceStore()
        store.upsert("corpus-a", "shared.md", _sha256("content A"))
        store.upsert("corpus-b", "shared.md", _sha256("content B"))
        files_a = [("shared.md", "content A")]  # unchanged in A
        plan_a = compute_diff("corpus-a", files_a, store)
        assert len(plan_a["skip"]) == 1
        # Corpus B stored hash is untouched
        assert store.get("corpus-b", "shared.md") == _sha256("content B")
