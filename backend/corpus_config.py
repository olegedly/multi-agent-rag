"""Corpus registry — single owner of ``corpora.yaml``.

Loads, validates, and resolves the YAML into typed ``Corpus`` objects.
Chunker strategy strings are resolved eagerly so bad names fail at startup.
Document globs are kept as strings for consumers to expand lazily.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

from backend.rag.chunker import Chunker, get_chunker


# ── Model ────────────────────────────────────────────────────────────────────


class Corpus(BaseModel):
    """A single corpus entry validated from ``corpora.yaml``.

    Serialises directly to JSON via ``model_dump()`` for the API endpoint.
    """

    id: str
    slug: str
    name: str
    description: str

    chunker: str
    """Chunker strategy name — resolved to a :class:`Chunker` instance by
    :class:`CorporaConfig`.  Stored here as a string so the model stays
    JSON-serialisable."""

    documents: str
    """Glob pattern relative to the project root, e.g. ``corpora/mcp-spec/*.md``."""

    # ── validators ────────────────────────────────────────────────────────

    @field_validator("chunker")
    @classmethod
    def _validate_chunker_name(cls, v: str) -> str:
        """Fail-fast for typo'd strategy names.

        Uses :func:`get_chunker` which raises ``ValueError`` for unknown
        strategies.  The instance is discarded — we only check the name here.
        """
        get_chunker(v)  # raises ValueError on bad names
        return v


# ── Config reader ────────────────────────────────────────────────────────────


class CorporaConfig:
    """Read, validate, and resolve ``corpora.yaml``.

    Usage::

        config = CorporaConfig()
        for corpus in config.list():
            print(corpus.name, corpus.slug)

        mcp = config.get("mcp-spec")
        chunker = config.get_chunker(mcp.slug)
        files = config.resolve_document_glob(mcp)
    """

    # ── construction ──────────────────────────────────────────────────────

    def __init__(self, yaml_path: str | Path | None = None) -> None:
        self._path = Path(yaml_path).resolve() if yaml_path else self._default_path()
        self._project_root = self._path.parent.parent  # backend/corpora.yaml → project root

        self._corpora: list[Corpus] = self._load()
        self._validate_uniqueness()

        # Eager chunker resolution — catches bad strategy names at startup.
        # Stored separately so ``Corpus`` stays JSON-serialisable.
        self._chunker_map: dict[str, Chunker] = {}
        self._resolve_chunkers()

    @classmethod
    def from_dicts(cls, corpora: list[dict]) -> "CorporaConfig":
        """Build a config from raw dicts (e.g. for testing).

        Skips YAML I/O and project-root detection.  Validation and chunker
        resolution still run.
        """
        instance = cls.__new__(cls)
        instance._path = None
        instance._project_root = Path.cwd()  # best guess; callers use get() / list()
        instance._corpora = [Corpus(**item) for item in corpora]
        instance._validate_uniqueness()
        instance._chunker_map = {}
        instance._resolve_chunkers()
        return instance

    @staticmethod
    def _default_path() -> Path:
        return Path(__file__).resolve().parent / "corpora.yaml"

    # ── load / validate ───────────────────────────────────────────────────

    def _load(self) -> list[Corpus]:
        if not self._path.exists():
            return []
        with open(self._path) as f:
            data = yaml.safe_load(f)
        raw = (data or {}).get("corpora", [])
        return [Corpus(**item) for item in raw]

    def _validate_uniqueness(self) -> None:
        slugs: set[str] = set()
        ids: set[str] = set()
        for c in self._corpora:
            if c.slug in slugs:
                raise ValueError(f"Duplicate slug in corpora.yaml: {c.slug!r}")
            if c.id in ids:
                raise ValueError(f"Duplicate id in corpora.yaml: {c.id!r}")
            slugs.add(c.slug)
            ids.add(c.id)

    def _resolve_chunkers(self) -> None:
        for c in self._corpora:
            self._chunker_map[c.slug] = get_chunker(c.chunker)

    # ── properties ──────────────────────────────────────────────────────────

    @property
    def project_root(self) -> Path:
        """Absolute path to the project root (parent of ``backend/``)."""
        return self._project_root

    # ── public accessors ──────────────────────────────────────────────────

    def list(self) -> list[Corpus]:
        """Return all configured corpora."""
        return list(self._corpora)

    def get(self, slug: str) -> Corpus | None:
        """Look up a corpus by slug."""
        for c in self._corpora:
            if c.slug == slug:
                return c
        return None

    def get_by_id(self, uuid: str) -> Corpus | None:
        """Look up a corpus by id."""
        for c in self._corpora:
            if c.id == uuid:
                return c
        return None

    def get_chunker(self, slug: str) -> Chunker | None:
        """Return the resolved chunker for a corpus slug."""
        return self._chunker_map.get(slug)

    def resolve_document_glob(self, corpus: Corpus) -> list[Path]:
        """Resolve the corpus's document glob relative to project root.

        Returns an empty list if no files match (the seed script will detect
        this later — the config layer doesn't fail on empty globs).
        """
        return sorted(self._project_root.glob(corpus.documents))
