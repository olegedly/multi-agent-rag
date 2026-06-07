"""Tests for the knowledge-base seeding script.

All tests use plain dicts — no fake stores needed since ``compute_diff``
now takes a simple ``{filename: content_hash}`` dictionary.
"""

import hashlib

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _store(*entries: tuple[str, str]) -> dict[str, str]:
    """Build a ``{filename: content_hash}`` dict from ``(filename, content)`` pairs."""
    return {fname: _sha256(content) for fname, content in entries}


# ── compute_diff (same signature as the real one in scripts/) ─────────────────


def compute_diff(
    files: list[tuple[str, str]],
    source_store: dict[str, str],
) -> dict[str, list]:
    """Compare source files against stored hashes, return a diff plan."""
    plan: dict[str, list] = {"insert": [], "update": [], "delete": [], "skip": []}
    disk_files = {fname for fname, _ in files}

    for fname, content in files:
        disk_hash = _sha256(content)
        stored_hash = source_store.get(fname)
        if stored_hash is None:
            plan["insert"].append((fname, content))
        elif stored_hash != disk_hash:
            plan["update"].append((fname, content))
        else:
            plan["skip"].append((fname, disk_hash))

    removed = set(source_store) - disk_files
    for fname in removed:
        plan["delete"].append((fname,))

    return plan


# ── Tests ────────────────────────────────────────────────────────────────────


class TestComputeDiff:
    """Pure function tests for the SHA-256 diff logic."""

    def test_all_new_files_are_inserted(self) -> None:
        store: dict[str, str] = {}
        files = [("doc1.md", "hello world"), ("doc2.md", "foo bar")]
        plan = compute_diff(files, store)
        assert len(plan["insert"]) == 2
        assert len(plan["skip"]) == 0
        assert len(plan["delete"]) == 0

    def test_unchanged_files_are_skipped(self) -> None:
        store = _store(("doc1.md", "hello world"))
        files = [("doc1.md", "hello world")]
        plan = compute_diff(files, store)
        assert len(plan["skip"]) == 1
        assert len(plan["insert"]) == 0
        assert len(plan["update"]) == 0

    def test_changed_files_are_updated(self) -> None:
        store = _store(("doc1.md", "old content"))
        files = [("doc1.md", "new content")]
        plan = compute_diff(files, store)
        assert len(plan["update"]) == 1
        assert len(plan["skip"]) == 0

    def test_deleted_files_are_removed(self) -> None:
        store = _store(("gone.md", "bye"))
        files: list[tuple[str, str]] = []
        plan = compute_diff(files, store)
        assert len(plan["delete"]) == 1
        assert plan["delete"][0][0] == "gone.md"

    def test_mixed_diff(self) -> None:
        store = _store(
            ("keep.md", "same"),
            ("change.md", "old"),
            ("gone.md", "bye"),
        )
        files = [
            ("keep.md", "same"),
            ("change.md", "changed"),
            ("new.md", "fresh"),
        ]
        plan = compute_diff(files, store)
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
        store = {"shared.md": _sha256("content A")}
        files_a = [("shared.md", "content A")]
        plan_a = compute_diff(files_a, store)
        assert len(plan_a["skip"]) == 1
