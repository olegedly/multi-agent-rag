"""SQLAlchemy ORM models for the multi-agent RAG system.

``Document`` stores chunked corpus content with vector embeddings,
scoped by ``corpus_id`` for multi-corpus isolation.  Each chunk
references a ``DocumentSource`` row via a composite foreign key
``(corpus_id, source_filename)`` with ``ON DELETE CASCADE``.

``DocumentSource`` tracks source file hashes (SHA-256) for idempotent
seeding — the seeding script uses this table to compute a diff
(insert new, update changed, delete removed, skip unchanged).
"""

import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_filename: Mapped[str] = mapped_column(String, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(VECTOR(768))
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(
            ["corpus_id", "source_filename"],
            ["document_sources.corpus_id", "document_sources.filename"],
            ondelete="CASCADE",
            name="fk_document_source",
        ),
    )


class DocumentSource(Base):
    __tablename__ = "document_sources"

    corpus_id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
