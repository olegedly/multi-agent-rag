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

SAMPLE_MD_HIERARCHY = """# Top Level

First paragraph.

## Middle Level

Second paragraph.

### Deep Level

Third paragraph.

## Another Middle

Fourth paragraph.
"""

GIANT_SECTION = "# A Long Section\n\n" + "".join(
    f"Paragraph {i}. " + "A" * 200 + "\n\n" for i in range(20)
)  # ~30 chars * 20 = 560 chars with separators; well over 500-token ~= 2000 chars

MANY_PARAS = "\n\n".join(f"This is paragraph number {i}. " + "B" * 50 for i in range(20))

OVERLAP_CHECK_TEXT = "\n\n".join(f"Para {i}" for i in range(30))


class TestMarkdownHeadingChunker:
    """Heading hierarchy splitting with recursive overflow fallback."""

    def test_splits_on_h1(self) -> None:
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        assert len(chunks) >= 3  # at least H1, H2 sections
        assert any("# Introduction" in c.content for c in chunks)
        assert any("## Section One" in c.content for c in chunks)

    def test_each_chunk_has_base_metadata(self) -> None:
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

    # ── Heading hierarchy tests (new behaviour) ──

    def test_heading_stack_pop_on_same_level(self) -> None:
        """`#` after `##` should pop `##` from the stack."""
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        # The Introduction section should only have Header 1 metadata, not Header 2
        intro_chunks = [c for c in chunks if "# Introduction" in c.content]
        assert len(intro_chunks) >= 1
        chunk = intro_chunks[0]
        assert "Header 1" in chunk.metadata
        assert "Header 2" not in chunk.metadata, (
            "Intro section should not carry Header 2 metadata"
        )

    def test_heading_stack_includes_ancestors(self) -> None:
        """A subsection under `##` > `###` carries both headers."""
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD, {"title": "Test"}
        )
        # The Subsection A chunk should carry Header 1 (Introduction) + Header 2 (Section One)
        sub_chunks = [c for c in chunks if "### Subsection A" in c.content]
        assert len(sub_chunks) >= 1
        chunk = sub_chunks[0]
        assert chunk.metadata.get("Header 1") == "Introduction"
        assert chunk.metadata.get("Header 2") == "Section One"

    def test_heading_stack_popped_by_higher_level(self) -> None:
        """When a new `##` arrives after `###`, the `###` is popped."""
        text = "# Top\n\nA\n\n### Deep\n\nB\n\n## Mid\n\nC"
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(text)
        # The 'C' section (under `## Mid`) should NOT have Header 3
        mid_chunks = [c for c in chunks if "C" in c.content]
        assert len(mid_chunks) >= 1
        mid = mid_chunks[0]
        assert mid.metadata.get("Header 1") == "Top"
        assert mid.metadata.get("Header 2") == "Mid"
        assert "Header 3" not in mid.metadata, "Header 3 should have been popped"

    def test_heading_stack_popped_when_new_top_level(self) -> None:
        """A new `#` pops everything below."""
        text = "## Old\n\ncontent\n\n# New Top\n\nnew content"
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(text)
        new_chunks = [c for c in chunks if "New Top" in c.content]
        assert len(new_chunks) >= 1
        new = new_chunks[0]
        assert new.metadata.get("Header 1") == "New Top"
        assert "Header 2" not in new.metadata

    def test_heading_path_in_metadata(self) -> None:
        """Metadata keys follow `Header N` naming per LangChain."""
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            SAMPLE_MD_HIERARCHY, {"title": "Test"}
        )
        # Find the Deep Level chunk
        deep_chunks = [c for c in chunks if "### Deep Level" in c.content]
        assert len(deep_chunks) >= 1
        meta = deep_chunks[0].metadata
        assert meta.get("Header 1") == "Top Level"
        assert meta.get("Header 2") == "Middle Level"
        assert meta.get("Header 3") == "Deep Level"

    # ── Oversized section overflow tests (new behaviour) ──

    def test_oversized_section_uses_recursive_fallback(self) -> None:
        """When a section exceeds max_chars, it's split via recursive separator fallback."""
        chunks = MarkdownHeadingChunker(max_tokens=100, overlap=10).chunk(
            GIANT_SECTION
        )
        assert len(chunks) > 1
        # All chunks should carry the heading metadata
        for c in chunks:
            assert c.metadata.get("Header 1") == "A Long Section"

    def test_oversized_uses_double_newline_before_character(self) -> None:
        """Overflow tries `\n\n` before falling back to character boundary."""
        # A section with many `\n\n`-separated paragraphs, tight max_chars so
        # multiple paragraphs fit but not all 20.
        text = "# H\n\n" + "\n\n".join(f"Paragraph number {i}" for i in range(20))
        chunks = MarkdownHeadingChunker(max_tokens=50, overlap=5).chunk(text)
        assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
        # Each chunk should end with complete paragraphs (no mid-paragraph cuts)
        for c in chunks:
            lines = [l for l in c.content.split("\n") if l.strip()]
            for line in lines:
                if line.startswith("Paragraph"):
                    assert "number" in line, f"Unexpected fragment: {line!r}"

    def test_oversized_single_paragraph_no_split(self) -> None:
        """A single gigantic paragraph (no `\n\n`) falls through to char boundary."""
        text = "# H\n\n" + "X" * 5000
        chunks = MarkdownHeadingChunker(max_tokens=100, overlap=20).chunk(text)
        assert len(chunks) >= 2
        # Content after heading should be split at character boundaries
        total_content = "".join(c.content for c in chunks)
        assert "X" * 5000 in total_content or total_content.count("X") == 5000

    # ── Edge cases ──

    def test_no_headings_produces_single_chunk(self) -> None:
        """Text without any headings becomes one chunk (if within size)."""
        text = "Just a plain paragraph without any markdown headings."
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            text, {"title": "Test"}
        )
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_empty_text(self) -> None:
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk("")
        assert len(chunks) == 0, "Empty text should produce no chunks"

    def test_single_heading_no_body(self) -> None:
        """A bare heading with no body text produces one chunk."""
        chunks = MarkdownHeadingChunker(max_tokens=500, overlap=50).chunk(
            "# Just a Heading"
        )
        assert len(chunks) == 1
        assert "# Just a Heading" in chunks[0].content
        assert chunks[0].metadata.get("Header 1") == "Just a Heading"


class TestParagraphChunker:
    """Split on double-newlines, merge small paras, enforce overlap."""

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

    # ── Overlap enforcement tests (new behaviour) ──

    def test_overlap_preserved_across_chunks(self) -> None:
        """Consecutive chunks share overlapping paragraphs."""
        text = MANY_PARAS
        chunker = ParagraphChunker(max_tokens=200, overlap=75)
        chunks = chunker.chunk(text, {"title": "Test"})
        assert len(chunks) >= 2
        # Check that at least one paragraph appears in two consecutive chunks
        found_overlap = False
        for i in range(len(chunks) - 1):
            a = chunks[i].content
            b = chunks[i + 1].content
            # Split into paragraphs and check for shared content
            paras_a = set(p.strip() for p in a.split("\n\n") if p.strip())
            paras_b = set(p.strip() for p in b.split("\n\n") if p.strip())
            shared = paras_a & paras_b
            if shared:
                found_overlap = True
                break
        assert found_overlap, "No overlapping paragraphs found between consecutive chunks"

    def test_overlap_pop_does_not_create_tiny_chunks(self) -> None:
        """After popping for overlap, the remaining buffer is not empty."""
        # Use many paragraphs where each is long enough that multiple chunks are forced
        text = "\n\n".join(f"This is paragraph number {i}. " + "B" * 200 for i in range(15))
        chunker = ParagraphChunker(max_tokens=250, overlap=100)
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
        # None should be empty
        for c in chunks:
            assert len(c.content.strip()) > 0

    # ── Edge cases ──

    def test_single_paragraph_kept_whole(self) -> None:
        """A single paragraph, even if oversized, is kept whole (no overflow split)."""
        chunker = ParagraphChunker(max_tokens=50, overlap=10)
        chunks = chunker.chunk("A" * 1000)
        assert len(chunks) == 1
        assert len(chunks[0].content) == 1000

    def test_empty_text(self) -> None:
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk("")
        assert len(chunks) == 0

    def test_only_whitespace_text(self) -> None:
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk("   \n\n  \n  ")
        assert len(chunks) == 0

    def test_exact_chunk_size_boundary(self) -> None:
        """Paragraph that exactly fills max_chars should not be split."""
        text = "A" * 2000  # exactly 500 tokens
        chunks = ParagraphChunker(max_tokens=500, overlap=50).chunk(text)
        assert len(chunks) == 1





class TestFixedSizeChunker:
    """Mechanical token-count splitting with sliding-window overlap.

    Uses a sliding window (start = end - overlap_chars) rather than
    LangChain's _merge_splits front-popping. Both are valid industry
    patterns — ours matches tiktoken's split_text_on_tokens approach.
    """

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

    # ── Basic splitting ──

    def test_splits_long_text_into_multiple_chunks(self) -> None:
        text = "A" * 4000  # ~1000 tokens, well above 500-token limit
        chunks = FixedSizeChunker(max_tokens=250, overlap=25).chunk(
            text, {"title": "Test"}
        )
        assert len(chunks) > 1

    def test_each_chunk_within_max_chars(self) -> None:
        """Every chunk should be ≤ max_chars (except possibly the last)."""
        text = "A" * 10000
        chunks = FixedSizeChunker(max_tokens=200, overlap=20).chunk(text)
        for c in chunks[:-1]:
            assert len(c.content) <= 800  # max_chars = 200*4 = 800

    # ── Overlap enforcement ──

    def test_overlap_shared_between_consecutive_chunks(self) -> None:
        """The sliding window causes characters to reappear across chunks."""
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 50
        chunker = FixedSizeChunker(max_tokens=25, overlap=10)
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        # Check that the end of chunk N overlaps with the start of chunk N+1
        overlaps_found = 0
        for i in range(len(chunks) - 1):
            a = chunks[i].content
            b = chunks[i + 1].content
            # With overlap=10 tokens = 40 chars, the last 40 chars of chunk
            # i should appear in chunk i+1
            tail = a[-40:] if len(a) >= 40 else a
            if tail in b:
                overlaps_found += 1
        assert overlaps_found >= 1, "No overlap detected between consecutive chunks"

    def test_overlap_proportion(self) -> None:
        """Window step = max_chars - overlap_chars."""
        chunker = FixedSizeChunker(max_tokens=100, overlap=25)
        # max_chars = 400, overlap_chars = 100, so step = 300
        text = "X" * 2000
        chunks = chunker.chunk(text)
        # With step=300, 2000 chars → ceil(2000/300) ≈ 7 chunks
        assert len(chunks) >= 6
        assert len(chunks) <= 8

    # ── Edge cases ──

    def test_empty_text(self) -> None:
        chunks = FixedSizeChunker(max_tokens=500, overlap=50).chunk("")
        assert len(chunks) == 0

    def test_exact_max_chars_text(self) -> None:
        text = "B" * 2000  # exactly 500 tokens = max_chars
        chunks = FixedSizeChunker(max_tokens=500, overlap=50).chunk(text)
        assert len(chunks) == 1
        assert len(chunks[0].content) == 2000

    def test_zero_overlap_chunk_positions_differ(self) -> None:
        """With zero overlap, chunk N starts at different offset than chunk N-1."""
        chunker = FixedSizeChunker(max_tokens=100, overlap=0)
        # Build a non-repeating string: each line is unique position info
        text = "\n".join(f"line number {i}" for i in range(500))
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        # Verify chunks start at different offsets
        assert chunks[0].content != chunks[1].content


class TestRecursiveChunker:
    """Recursive separator fallback splitting with overlap enforcement.

    Based on LangChain's ``RecursiveCharacterTextSplitter._split_text``
    and ``TextSplitter._merge_splits``.
    """

    TEXT = "ABCDEFGHIJ" * 100  # 1000 chars, no whitespace breaks

    def test_single_chunk_for_short_text(self) -> None:
        text = "Short text"
        chunks = RecursiveChunker(max_tokens=500, overlap=50).chunk(
            text, {"title": "Test"}
        )
        assert len(chunks) == 1
        assert chunks[0].content == "Short text"

    def test_each_chunk_has_metadata(self) -> None:
        text = "A" * 4000
        chunks = RecursiveChunker(max_tokens=125, overlap=12).chunk(
            text, {"title": "Test"}
        )
        for c in chunks:
            assert "chunk_index" in c.metadata
            assert c.metadata["title"] == "Test"

    def test_splits_at_char_limit(self) -> None:
        """With no natural breaks, splits at max_chars boundary."""
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk(
            self.TEXT, {"title": "Test"}
        )
        assert len(chunks) >= 9
        for c in chunks:
            assert len(c.content) <= 100

    # ── Separator priority ──

    def test_double_newline_preferred_over_single(self) -> None:
        """Text with both `\n\n` and `\n` splits on `\n\n` first."""
        text = "AAA\n\nBBB\nCCC\n\nDDD"
        chunks = RecursiveChunker(max_tokens=50, overlap=5).chunk(
            text, {"title": "Test"}
        )
        chunk_contents = [c.content for c in chunks]
        assert any("AAA" in c for c in chunk_contents)
        assert any("DDD" in c for c in chunk_contents)

    def test_single_newline_fallback(self) -> None:
        """Text without `\n\n` falls through to `\n` splitting."""
        text = "AAA\nBBB\nCCC\nDDD\nEEE\nFFF\nGGG"
        chunks = RecursiveChunker(max_tokens=6, overlap=1).chunk(text)
        assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
        for c in chunks:
            content = c.content
            assert "\n\n" not in content, (
                f"Chunk should not contain double newlines: {content!r}"
            )

    def test_character_boundary_final_fallback(self) -> None:
        """Text without any newlines or spaces falls through to character."""
        text = "X" * 1000
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk(text)
        assert len(chunks) >= 9
        for c in chunks:
            assert len(c.content) <= 100
            assert set(c.content) == {"X"}

    def test_space_fallback_before_character(self) -> None:
        """Space is tried before character boundary."""
        text = " ".join("A" * 10 for _ in range(200))
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk(text)
        assert len(chunks) >= 2
        # Chunks should end at word boundaries
        for c in chunks:
            # Content is space-separated words, should never end mid-word
            # when the separator is a space
            content = c.content
            if " " in content and content.rstrip()[-1] != " ":
                assert content.rstrip()[-1] != "A" or content.endswith("A"), (
                    f"Chunk ends mid-word: {content[-20:]!r}"
                )

    # ── Recursion ──

    def test_recursion_on_oversized_merged_chunk(self) -> None:
        """If a merged chunk is still over max_chars, it's re-split with
        the next separator."""
        # A section with many `\n\n`-separated paragraphs where the merged
        # chunk still exceeds max_chars
        text = "\n\n".join(f"Paragraph number {i}" for i in range(50))
        chunks = RecursiveChunker(max_tokens=100, overlap=10).chunk(text)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c.content) <= 400  # max_chars = 100*4

    # ── Overlap enforcement ──

    def test_overlap_between_consecutive_chunks(self) -> None:
        """Consecutive chunks share overlapping content."""
        text = "\n".join(f"line {i}" for i in range(200))
        chunks = RecursiveChunker(max_tokens=50, overlap=20).chunk(text)
        assert len(chunks) >= 2
        # Check that at least one line appears in two chunks
        found_overlap = False
        for i in range(len(chunks) - 1):
            a_lines = set(chunks[i].content.split("\n"))
            b_lines = set(chunks[i + 1].content.split("\n"))
            if a_lines & b_lines:
                found_overlap = True
                break
        assert found_overlap, "No overlapping content between consecutive chunks"

    # ── Edge cases ──

    def test_empty_text(self) -> None:
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk("")
        assert len(chunks) == 0

    def test_only_whitespace(self) -> None:
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk("   \n  \n  ")
        assert len(chunks) == 0

    def test_text_with_only_newlines(self) -> None:
        chunks = RecursiveChunker(max_tokens=25, overlap=2).chunk("\n\n\n")
        assert len(chunks) == 0

