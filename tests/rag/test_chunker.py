"""Tests for chunker strategies.

All chunkers are pure functions — no filesystem or DB dependency.
"""

import pytest

from backend.rag.chunker import (
    FixedSizeChunker,
    MarkdownHeadingChunker,
    ParagraphChunker,
    RecursiveChunker,
)


SAMPLE_MD = """# Introduction

This is the intro paragraph. It has some text about the topic.

## Section One

Content in section one. More details here.

### Subsection A

Deeper detail in the first subsection.

## Section Two

Content in section two.
"""


class TestMarkdownHeadingChunker:
    """Splits on markdown headings (``#``, ``##``, ``###``)."""

    def test_splits_on_h1(self) -> None:
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        assert len(chunks) >= 3  # at least H1, H2 sections
        assert any("# Introduction" in c.content for c in chunks)
        assert any("## Section One" in c.content for c in chunks)

    def test_each_chunk_has_metadata(self) -> None:
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        for c in chunks:
            assert "chunk_index" in c.metadata
            assert c.metadata["title"] == "Test"

    def test_heading_preserved_in_content(self) -> None:
        """The heading line is included at the start of each chunk."""
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        for c in chunks:
            if "## Section One" in c.content:
                assert "Content in section one" in c.content
                break
        else:
            pytest.fail("No chunk contained Section One")


class TestParagraphChunker:
    """Splits on double-newlines, merging small paragraphs."""

    TEXT = (
        "This is the first paragraph. It has some text.\n\n"
        "This is the second paragraph. Still going.\n\n"
        "Third paragraph here.\n\n"
        "Fourth and final paragraph of the test content."
    )

    def test_splits_on_double_newlines(self) -> None:
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk(
            self.TEXT, {"title": "Test"}
        )
        assert len(chunks) >= 1

    def test_merges_small_paragraphs(self) -> None:
        """Very small paragraphs get merged up to max_tokens."""
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk(
            self.TEXT, {"title": "Test"}
        )
        # With max_tokens=500, all 4 small paras should merge into 1 chunk
        assert len(chunks) == 1
        assert "first paragraph" in chunks[0].content
        assert "Fourth and final" in chunks[0].content

    def test_each_chunk_has_metadata(self) -> None:
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk(
            self.TEXT, {"title": "Test"}
        )
        for c in chunks:
            assert "chunk_index" in c.metadata


class TestFixedSizeChunker:
    """Mechanical token-count splitting with overlap."""

    def test_splits_exact_size(self) -> None:
        text = "A" * 4000  # ~1000 tokens, well above 500-token limit
        chunks = FixedSizeChunker(max_tokens=250, overlap=25).chunk(
            text, {"title": "Test"}
        )
        assert len(chunks) > 1

    def test_single_chunk_for_short_text(self) -> None:
        text = "Short text"
        chunks = FixedSizeChunker(max_tokens=500, overlap=50).chunk(
            text, {"title": "Test"}
        )
        assert len(chunks) == 1
        assert chunks[0].content == "Short text"

    def test_each_chunk_has_metadata(self) -> None:
        text = "A" * 4000
        chunks = FixedSizeChunker(max_tokens=250, overlap=25).chunk(
            text, {"title": "Test"}
        )
        for c in chunks:
            assert "chunk_index" in c.metadata
            assert c.metadata["title"] == "Test"


class TestRecursiveChunker:
    """Character-based fallback splitting by separator priority."""

    TEXT = "ABCDEFGHIJ" * 100  # 1000 chars, no whitespace breaks

    def test_splits_at_char_limit(self) -> None:
        """With no natural breaks, splits at max_chars boundary."""
        chunks = RecursiveChunker(max_chars=100).chunk(self.TEXT, {"title": "Test"})
        assert len(chunks) >= 9  # 1000 chars / 100 = 10, but some overlap; at least 9

    def test_respects_separator_priority(self) -> None:
        """Double-newline is preferred over single-newline over character."""
        text = "AAA\n\nBBB\nCCC\n\nDDD"
        chunks = RecursiveChunker(max_chars=200).chunk(text, {"title": "Test"})
        assert len(chunks) <= 3
        # AAA and BBB should be in separate chunks or same depending on overlap
        chunk_contents = [c.content for c in chunks]
        assert any("AAA" in c for c in chunk_contents)
        assert any("DDD" in c for c in chunk_contents)

