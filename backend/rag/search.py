"""Semantic vector search and document retrieval for RAG.

Provides two corpus-scoped operations:
- ``search_corpus``: Embed a query and return ranked chunks via cosine similarity.
- ``read_document``: Return all chunks from the same source file(s) as given chunk IDs.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy import text

from backend.embeddings.protocol import EmbeddingClient


@runtime_checkable
class AsyncSession(Protocol):
    """Minimal async session protocol — just what ``search.py`` needs.

    Narrower than SQLAlchemy's full ``AsyncSession`` — only the methods
    this module actually calls.
    """

    async def execute(self, statement: object, parameters: object | None = None) -> Any: ...
    async def __aenter__(self) -> "AsyncSession": ...
    async def __aexit__(self, *args: object) -> None: ...


@runtime_checkable
class AsyncSessionMaker(Protocol):
    """Minimal sessionmaker protocol — callable returning an async session."""

    def __call__(self, **kwargs: Any) -> AsyncSession: ...


class SearchResult(BaseModel):
    """A single chunk returned from a corpus search or document read."""

    id: int
    corpus_id: str
    content: str
    metadata: dict
    score: float | None = None


async def search_corpus(
    query: str,
    corpus_id: str,
    top_k: int,
    embedding_client: EmbeddingClient,
    sessionmaker: AsyncSessionMaker,
) -> list[SearchResult]:
    """Semantic search over a single corpus.

    Embeds *query* via *embedding_client*, then runs a cosine-similarity
    (``<=>``) query against the ``documents`` table filtered by *corpus_id*.

    Returns up to *top_k* results sorted by descending similarity.  Score is
    ``1 - cosine_distance``, in range ``[0, 1]`` where higher is more similar.
    """
    vecs = await embedding_client.embed_texts([query])
    query_vec = vecs[0]

    async with sessionmaker() as session:
        sql = text(
            """
            SELECT id, corpus_id, content, metadata,
                   1 - (embedding <=> :query_vec) AS score
            FROM documents
            WHERE corpus_id = :corpus_id
            ORDER BY embedding <=> :query_vec
            LIMIT :top_k
            """
        )
        rows = await session.execute(
            sql,
            {
                "query_vec": query_vec,
                "corpus_id": corpus_id,
                "top_k": top_k,
            },
        )
        results = []
        for row in rows:
            meta = row.metadata if isinstance(row.metadata, dict) else {}
            results.append(
                SearchResult(
                    id=row.id,
                    corpus_id=row.corpus_id,
                    content=row.content,
                    metadata=meta,
                    score=float(row.score) if row.score is not None else None,
                )
            )
        return results


async def read_document(
    chunk_ids: list[int],
    corpus_id: str,
    sessionmaker: AsyncSessionMaker,
) -> list[SearchResult]:
    """Return all chunks from the same source file(s) as the given chunk IDs.

    Given one or more chunk IDs, looks up their source filenames and returns
    *every* chunk from those files within the same corpus.  This lets a user
    start from a search hit and expand to full document context.

    Cross-corpus chunk IDs that don't belong to *corpus_id* are silently
    excluded, yielding an empty result list.
    """
    async with sessionmaker() as session:
        sql = text(
            """
            SELECT id, corpus_id, content, metadata
            FROM documents
            WHERE corpus_id = :corpus_id
              AND source_filename IN (
                  SELECT DISTINCT source_filename
                  FROM documents
                  WHERE id = ANY(:chunk_ids)
                    AND corpus_id = :corpus_id
              )
            """
        )
        rows = await session.execute(
            sql,
            {
                "chunk_ids": list(chunk_ids),
                "corpus_id": corpus_id,
            },
        )
        results = []
        for row in rows:
            meta = row.metadata if isinstance(row.metadata, dict) else {}
            results.append(
                SearchResult(
                    id=row.id,
                    corpus_id=row.corpus_id,
                    content=row.content,
                    metadata=meta,
                    score=None,
                )
            )
        return results
