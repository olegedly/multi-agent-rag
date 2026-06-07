"""Tests for database models.

Verifies schema shape via instantiation and column inspection.
No database required — pure SQLAlchemy metadata assertions.
"""

from typing import cast

from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import JSONB

from backend.models import Document, DocumentSource


class TestDocumentModel:
    """Document table stores chunked corpus content with vector embeddings."""

    def test_has_required_columns(self) -> None:
        assert hasattr(Document, "id")
        assert hasattr(Document, "corpus_id")
        assert hasattr(Document, "content")
        assert hasattr(Document, "embedding")
        assert hasattr(Document, "doc_metadata")

    def test_corpus_id_is_indexed(self) -> None:
        """corpus_id has a plain B-tree index for filtering."""
        table = cast(Table, Document.__table__)
        corpus_indexes = [idx for idx in table.indexes if "corpus_id" in idx.columns]
        assert len(corpus_indexes) >= 1, "corpus_id should have at least one index"

    def test_metadata_is_jsonb(self) -> None:
        """metadata column uses PostgreSQL JSONB."""
        col = cast(Column, Document.__table__.c["metadata"])
        assert isinstance(col.type, JSONB), "metadata should be JSONB"

    def test_embedding_is_vector(self) -> None:
        """embedding uses pgvector VECTOR(768)."""
        col = cast(Column, Document.__table__.c["embedding"])
        type_str = str(col.type)
        assert "VECTOR" in type_str.upper() or "vector" in type_str.lower()

    def test_can_instantiate_with_fields(self) -> None:
        doc = Document(
            corpus_id="test-corpus",
            content="Some chunked content",
            doc_metadata={"title": "Test Doc", "source_url": "https://example.com", "chunk_index": 0},
        )
        assert doc.corpus_id == "test-corpus"
        assert "chunk_index" in doc.doc_metadata

    def test_content_not_nullable(self) -> None:
        col = cast(Column, Document.__table__.c["content"])
        assert not col.nullable, "content should be NOT NULL"


class TestDocumentSourceModel:
    """DocumentSource tracks source file hashes for idempotent seeding."""

    def test_has_required_columns(self) -> None:
        assert hasattr(DocumentSource, "corpus_id")
        assert hasattr(DocumentSource, "filename")
        assert hasattr(DocumentSource, "content_hash")
        assert hasattr(DocumentSource, "updated_at")

    def test_compound_primary_key(self) -> None:
        """Primary key is (corpus_id, filename)."""
        table = cast(Table, DocumentSource.__table__)
        pk_cols = {col.name for col in table.primary_key.columns}
        assert pk_cols == {"corpus_id", "filename"}, (
            f"Expected PK=(corpus_id, filename), got {pk_cols}"
        )

    def test_updated_at_has_server_default(self) -> None:
        """updated_at has server_default=func.now() for DB-side timestamp."""
        col = cast(Column, DocumentSource.__table__.c["updated_at"])
        assert col.server_default is not None, "updated_at should have server_default"

    def test_can_instantiate(self) -> None:
        source = DocumentSource(
            corpus_id="test-corpus",
            filename="path/to/doc.md",
            content_hash="sha256hash123",
        )
        assert source.corpus_id == "test-corpus"
        assert source.filename == "path/to/doc.md"
        assert source.content_hash == "sha256hash123"
