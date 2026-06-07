"""Per-corpus chunking strategies for RAG document ingestion.

Each chunker implements the ``Chunker`` protocol and targets ~500 tokens
with 50-token overlap. Token count is approximated by character count ÷ 4.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Chunk:
    """A single chunk of document content with metadata."""

    content: str
    metadata: dict = field(default_factory=dict)


class Chunker(Protocol):
    """Protocol that all chunker strategies satisfy."""

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        """Split *text* into a list of :class:`Chunk` objects.

        Parameters
        ----------
        text : str
            The full document text to chunk.
        metadata : dict, optional
            Base metadata to attach to each chunk (e.g. ``title``, ``source_url``).
            Each chunk also gets a ``chunk_index`` key injected.

        Returns
        -------
        list[Chunk]
            Ordered list of chunks covering *text*.
        """
        ...


def _approx_tokens(text: str) -> int:
    """Rough token count: characters ÷ 4."""
    return len(text) // 4


def _tag_chunks(chunks: list[Chunk], base_meta: dict | None, start_index: int = 0) -> None:
    """Inject base metadata and sequential ``chunk_index`` into each chunk."""
    meta = dict(base_meta or {})
    for i, chunk in enumerate(chunks):
        merged = {**meta, "chunk_index": start_index + i}
        chunk.metadata = {**merged, **chunk.metadata}


# ── Strategies ────────────────────────────────────────────────────────────────


class MarkdownHeadingChunker:
    """Split on markdown headings (``#``/``##``/``###``), then recursively.

    Each top- or second-level heading becomes the start of a new section.
    If a section exceeds max_tokens, it is further split by the next heading
    depth. Remaining over-large sections fall through to paragraph splitting.
    """

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        raw: list[Chunk] = []
        lines = text.split("\n")
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Any heading level triggers a section break
            if stripped.startswith("#"):
                if current_lines:
                    raw.append(Chunk(content="\n".join(current_lines)))
                    current_lines = []
                current_lines.append(line)
            else:
                current_lines.append(line)

        # Flush remaining
        if current_lines:
            raw.append(Chunk(content="\n".join(current_lines)))

        # Apply max_chars split per raw chunk
        result: list[Chunk] = []
        for chunk in raw:
            if len(chunk.content) <= self.max_chars:
                result.append(chunk)
            else:
                result.extend(self._split_overflow(chunk.content))

        _tag_chunks(result, metadata)
        return result

    def _split_overflow(self, text: str) -> list[Chunk]:
        """Split over-large text by character boundary with overlap."""
        chunks: list[Chunk] = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            chunks.append(Chunk(content=text[start:end]))
            start = end - self.overlap_chars if end < len(text) else len(text)
        return chunks


class ParagraphChunker:
    """Split on double-newlines, merging small paragraphs up to max_tokens."""

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        paragraphs = text.split("\n\n")
        result: list[Chunk] = []
        buffer: list[str] = []

        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                continue
            # Estimate combined size if we add this para
            candidate = "\n\n".join(buffer + [stripped]) if buffer else stripped
            if len(candidate) > self.max_chars and buffer:
                # Flush buffer
                result.append(Chunk(content="\n\n".join(buffer)))
                buffer = [stripped]
            else:
                buffer.append(stripped)

        if buffer:
            result.append(Chunk(content="\n\n".join(buffer)))

        _tag_chunks(result, metadata)
        return result


class RecursiveChunker:
    """Character-based fallback splitting by separator priority.

    Tries double-newline first, then single-newline, then character boundary.
    """

    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        if len(text) <= self.max_chars:
            result = [Chunk(content=text)]
            _tag_chunks(result, metadata)
            return result

        # Try double-newline split
        parts = text.split("\n\n")
        if len(parts) > 1:
            return self._merge_parts(parts, "\n\n", metadata)

        # Try single-newline split
        parts = text.split("\n")
        if len(parts) > 1:
            return self._merge_parts(parts, "\n", metadata)

        # Character boundary
        return self._char_split(text, metadata)

    def _merge_parts(self, parts: list[str], separator: str, metadata: dict | None) -> list[Chunk]:
        result: list[Chunk] = []
        buffer: list[str] = []

        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            candidate = separator.join(buffer + [stripped]) if buffer else stripped
            if len(candidate) > self.max_chars and buffer:
                result.append(Chunk(content=separator.join(buffer)))
                buffer = [stripped]
            else:
                buffer.append(stripped)

        if buffer:
            result.append(Chunk(content=separator.join(buffer)))

        _tag_chunks(result, metadata)
        return result

    def _char_split(self, text: str, metadata: dict | None) -> list[Chunk]:
        result: list[Chunk] = []
        for i in range(0, len(text), self.max_chars):
            result.append(Chunk(content=text[i : i + self.max_chars]))
        _tag_chunks(result, metadata)
        return result
