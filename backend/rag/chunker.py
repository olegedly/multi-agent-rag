"""Per-corpus chunking strategies for RAG document ingestion.

Each chunker implements the ``Chunker`` protocol and targets ~500 tokens
with 50-token overlap. Token count is approximated by character count ÷ 4.
"""

import re
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


def _tag_chunks(chunks: list[Chunk], base_meta: dict | None, start_index: int = 0) -> None:
    """Inject base metadata and sequential ``chunk_index`` into each chunk."""
    meta = dict(base_meta or {})
    for i, chunk in enumerate(chunks):
        merged = {**meta, "chunk_index": start_index + i}
        chunk.metadata = {**merged, **chunk.metadata}


# ── Strategies ────────────────────────────────────────────────────────────────


_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)")


class MarkdownHeadingChunker:
    """Split markdown files by heading hierarchy with recursive separator fallback.

    Maintains a heading stack by depth level. When a heading at the same
    or higher level arrives, lower-depth headers are popped from the stack.
    Content accumulates under the current heading path (e.g. ``Header 1`` /
    ``Header 2`` keys in each chunk's metadata).

    Oversized sections are further split using recursive separator fallback:
    double-newline first, then single-newline, then character boundary.

    Based on LangChain's ``MarkdownHeaderTextSplitter`` with the addition of
    size enforcement via ``RecursiveCharacterTextSplitter``-style fallback.
    """

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        sections = self._split_by_headings(text)

        result: list[Chunk] = []
        for section_text, heading_meta in sections:
            if not section_text.strip():
                continue
            if len(section_text) <= self.max_chars:
                result.append(Chunk(content=section_text, metadata=dict(heading_meta)))
            else:
                result.extend(self._split_oversized(section_text, heading_meta))

        _tag_chunks(result, metadata)
        return result

    def _split_by_headings(
        self, text: str
    ) -> list[tuple[str, dict[str, str]]]:
        """Split *text* into heading-delimited sections with hierarchy metadata.

        Maintains a ``(depth, header_text)`` stack.  When a heading at the
        same or higher level arrives, headers at that depth and deeper are
        popped.  Each section carries the full heading path as metadata
        (e.g. ``{"Header 1": "Intro", "Header 2": "Details"}``).

        Based on LangChain's ``MarkdownHeaderTextSplitter.split_text``.
        """
        lines = text.split("\n")
        sections: list[tuple[str, dict[str, str]]] = []
        header_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []

        for line in lines:
            match = _HEADER_RE.match(line)
            if not match:
                current_lines.append(line)
                continue

            # Flush current section before switching to new heading
            if current_lines:
                heading_meta: dict[str, str] = {}
                for depth, hdr_text in header_stack:
                    heading_meta[f"Header {depth}"] = hdr_text
                sections.append(("\n".join(current_lines), heading_meta))
                current_lines = []

            # Update heading stack (LangChain pattern: pop same-or-higher level)
            depth = len(match.group(1))
            header_text = match.group(2).strip()
            while header_stack and header_stack[-1][0] >= depth:
                header_stack.pop()
            header_stack.append((depth, header_text))

            # Include the heading line in content
            current_lines.append(line)

        # Flush remaining content
        if current_lines:
            heading_meta = {}
            for depth, hdr_text in header_stack:
                heading_meta[f"Header {depth}"] = hdr_text
            sections.append(("\n".join(current_lines), heading_meta))

        return sections

    def _split_oversized(
        self, text: str, heading_meta: dict[str, str]
    ) -> list[Chunk]:
        """Split *text* that exceeds ``max_chars`` using recursive separator
        fallback (double-newline → single-newline → character boundary).

        Based on LangChain's ``RecursiveCharacterTextSplitter._split_text``.
        """
        raw = self._recurse_split(text, 0)
        return [Chunk(content=r, metadata=dict(heading_meta)) for r in raw]

    def _recurse_split(self, text: str, sep_idx: int) -> list[str]:
        """Recursive separator fallback, modelled on LangChain's pattern.

        Returns a flat list of text chunks.
        """
        if len(text) <= self.max_chars:
            return [text]

        separators = ["\n\n", "\n", " "]
        if sep_idx >= len(separators):
            # Final fallback: character boundary
            return [text[i:i + self.max_chars] for i in range(0, len(text), self.max_chars)]

        sep = separators[sep_idx]
        splits = text.split(sep)
        if len(splits) <= 1:
            return self._recurse_split(text, sep_idx + 1)

        result: list[str] = []
        buffer: list[str] = []
        buffer_len = 0
        sep_len = len(sep)

        for s in splits:
            if not s.strip():
                continue
            s_len = len(s)
            add_sep = sep_len if buffer else 0

            if buffer and buffer_len + add_sep + s_len > self.max_chars:
                # Flush buffer
                result.append(sep.join(buffer))
                # Pop from front for overlap (LangChain _merge_splits pattern)
                while buffer and buffer_len > self.overlap_chars:
                    removed = buffer.pop(0)
                    buffer_len -= len(removed) + (sep_len if buffer else 0)

            buffer.append(s)
            buffer_len += s_len + (sep_len if len(buffer) > 1 else 0)

        if buffer:
            result.append(sep.join(buffer))

        # Recurse on any chunk that is still too large
        final: list[str] = []
        for chunk in result:
            if len(chunk) > self.max_chars:
                final.extend(self._recurse_split(chunk, sep_idx + 1))
            else:
                final.append(chunk)
        return final


class ParagraphChunker:
    """Split on double-newlines, merging small paragraphs up to max_tokens.

    When a chunk is flushed, the overlap is enforced by popping paragraphs
    from the front of the accumulator buffer — modelled on LangChain's
    ``TextSplitter._merge_splits``.
    """

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        paragraphs = text.split("\n\n")
        result: list[Chunk] = []
        buffer: list[str] = []
        buffer_len = 0
        sep = "\n\n"
        sep_len = len(sep)

        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                continue
            p_len = len(stripped)
            add_sep = sep_len if buffer else 0

            if buffer and buffer_len + add_sep + p_len > self.max_chars:
                # Flush buffer as a chunk
                result.append(Chunk(content=sep.join(buffer)))

                # LangChain _merge_splits overlap: pop from front until
                # remaining ≤ overlap_chars
                while buffer and buffer_len > self.overlap_chars:
                    removed = buffer.pop(0)
                    buffer_len -= len(removed) + (sep_len if buffer else 0)

            buffer.append(stripped)
            buffer_len += p_len + (sep_len if len(buffer) > 1 else 0)

        if buffer:
            result.append(Chunk(content=sep.join(buffer)))

        _tag_chunks(result, metadata)
        return result


class FixedSizeChunker:
    """Mechanical token-count splitting with overlap.

    Splits text into fixed-size chunks by character count
    (approximated as ``max_tokens * 4``), with configurable
    overlap. No awareness of structure — pure byte slicing.
    """

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        if not text:
            return []

        if len(text) <= self.max_chars:
            result = [Chunk(content=text)]
            _tag_chunks(result, metadata)
            return result

        chunks: list[Chunk] = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            chunks.append(Chunk(content=text[start:end]))
            start = end - self.overlap_chars if end < len(text) else len(text)

        _tag_chunks(chunks, metadata)
        return chunks


class RecursiveChunker:
    """Recursive separator fallback splitting with overlap enforcement.

    Tries separators in priority order:
      1. ``\n\n`` (paragraph boundary)
      2. ``\n`` (line boundary)
      3. `` `` (word boundary)
      4. character boundary (final fallback)

    Merges small fragments up to ``max_chars`` and enforces overlap by
    popping from the front of the accumulator.  Oversized chunks are
    recursively re-split with the next separator.

    Based on LangChain's ``RecursiveCharacterTextSplitter._split_text``
    and ``TextSplitter._merge_splits``.
    """

    _SEPARATORS = ["\n\n", "\n", " "]

    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap * 4

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        if not text or not text.strip():
            return []

        raw = self._split(text, self._SEPARATORS)
        result = [Chunk(content=r) for r in raw]
        _tag_chunks(result, metadata)
        return result

    def _split(self, text: str, separators: list[str]) -> list[str]:
        """Recursive separator fallback — modelled on LangChain's ``_split_text``.

        Returns a flat list of text chunks, each ≤ ``max_chars``.
        """
        if len(text) <= self.max_chars:
            return [text]
        if not separators:
            # Final fallback: character boundary
            return [text[i:i + self.max_chars] for i in range(0, len(text), self.max_chars)]

        sep = separators[0]
        rest = separators[1:]

        # If the separator doesn't appear in the text, try the next one
        if sep not in text:
            return self._split(text, rest)

        splits = text.split(sep)
        # Filter empty parts
        splits = [s for s in splits if s.strip()]

        # Merge small splits into chunks, enforcing overlap
        merged = self._merge_splits(splits, sep)

        # Recurse on any chunk that is still too large
        final: list[str] = []
        for chunk in merged:
            if len(chunk) > self.max_chars and rest:
                final.extend(self._split(chunk, rest))
            elif len(chunk) > self.max_chars:
                # No more separators — character boundary
                final.extend(
                    chunk[i:i + self.max_chars]
                    for i in range(0, len(chunk), self.max_chars)
                )
            else:
                final.append(chunk)
        return final

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """Merge small fragments into chunks ≤ ``max_chars`` with overlap
        enforced by popping from the front of the accumulator.

        Based on LangChain's ``TextSplitter._merge_splits``.
        """
        docs: list[str] = []
        buffer: list[str] = []
        buffer_len = 0
        sep_len = len(separator)

        for s in splits:
            s_len = len(s)
            add_sep = sep_len if buffer else 0

            if buffer and buffer_len + add_sep + s_len > self.max_chars:
                # Flush buffer
                docs.append(separator.join(buffer))
                # Pop from front until remaining ≤ overlap_chars
                while buffer and buffer_len > self.overlap_chars:
                    removed = buffer.pop(0)
                    buffer_len -= len(removed) + (sep_len if buffer else 0)

            buffer.append(s)
            buffer_len += s_len + (sep_len if len(buffer) > 1 else 0)

        if buffer:
            docs.append(separator.join(buffer))

        return docs


# ── Strategy resolution ──────────────────────────────────────────────────────


def get_chunker(
    strategy: str,
    max_tokens: int = 500,
    overlap: int = 50,
) -> Chunker:
    """Return a chunker instance for the given strategy name.

    Parameters
    ----------
    strategy : str
        One of ``"markdown-heading"``, ``"paragraph"``, ``"recursive"``,
        or ``"fixed-size"``.
    max_tokens : int
        Target chunk size in tokens (default 500).
    overlap : int
        Tokens of overlap between chunks (default 50).

    Returns
    -------
    Chunker
        An instance of the matching chunker class.

    Raises
    ------
    ValueError
        If *strategy* is not recognised.
    """
    if strategy == "markdown-heading":
        return MarkdownHeadingChunker(max_tokens=max_tokens, overlap=overlap)
    elif strategy == "paragraph":
        return ParagraphChunker(max_tokens=max_tokens, overlap=overlap)
    elif strategy == "recursive":
        return RecursiveChunker(max_tokens=max_tokens, overlap=overlap)
    elif strategy == "fixed-size":
        return FixedSizeChunker(max_tokens=max_tokens, overlap=overlap)
    else:
        raise ValueError(f"Unknown chunker strategy: {strategy!r}")
