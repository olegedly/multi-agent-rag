"""Tests for the ``CorporaConfig`` module.

Uses ``from_dicts()`` to avoid YAML I/O in unit tests — the YAML-reading
path is exercised by a single integration test with a real file.
"""

import pytest
from pydantic import ValidationError

from backend.corpus_config import CorporaConfig, Corpus


SAMPLE_CORPORA = [
    {
        "id": "a1b2c3d4-1234-5678-9abc-def012345678",
        "slug": "mcp-spec",
        "name": "MCP Specification",
        "description": "MCP spec and ADK documentation",
        "chunker": "markdown-heading",
        "documents": "corpora/mcp-spec/*.md",
    },
    {
        "id": "b2c3d4e5-2345-6789-abcd-ef0123456789",
        "slug": "eu-ai-act",
        "name": "EU AI Act",
        "description": "European Union AI regulation",
        "chunker": "paragraph",
        "documents": "corpora/eu-ai-act/*.md",
    },
]


# ── Corpus model ──────────────────────────────────────────────────────────────


class TestCorpusModel:
    def test_validates_chunker_strategy(self) -> None:
        """Bad strategy names raise Pydantic ValidationError."""
        with pytest.raises(ValidationError, match="chunker"):
            Corpus(
                id="x",
                slug="x",
                name="X",
                description="",
                chunker="bogus-strategy",
                documents="*.md",
            )

    def test_valid_chunker_passes(self) -> None:
        c = Corpus(
            id="x",
            slug="x",
            name="X",
            description="",
            chunker="recursive",
            documents="*.md",
        )
        assert c.chunker == "recursive"

    def test_serialises_as_dict(self) -> None:
        c = Corpus(
            id="x",
            slug="x",
            name="X",
            description="desc",
            chunker="paragraph",
            documents="*.md",
        )
        d = c.model_dump()
        assert d["id"] == "x"
        assert d["chunker"] == "paragraph"
        assert d["documents"] == "*.md"


# ── CorporaConfig ─────────────────────────────────────────────────────────────


class TestCorporaConfigFromDicts:
    def test_list_returns_all_corpora(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        corpora = config.list()
        assert len(corpora) == 2

    def test_get_by_slug(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        c = config.get("mcp-spec")
        assert c is not None
        assert c.name == "MCP Specification"

    def test_get_returns_none_for_missing_slug(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        assert config.get("nonexistent") is None

    def test_get_by_id(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        uuid = "b2c3d4e5-2345-6789-abcd-ef0123456789"
        c = config.get_by_id(uuid)
        assert c is not None
        assert c.slug == "eu-ai-act"

    def test_get_by_id_returns_none_for_missing(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        assert config.get_by_id("missing") is None

    def test_get_chunker_returns_instance(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        chunker = config.get_chunker("mcp-spec")
        assert chunker is not None
        assert hasattr(chunker, "chunk")

    def test_get_chunker_returns_none_for_missing_slug(self) -> None:
        config = CorporaConfig.from_dicts(SAMPLE_CORPORA)
        assert config.get_chunker("nonexistent") is None

    def test_duplicate_slug_raises(self) -> None:
        """Duplicate slugs are caught at config construction time."""
        with pytest.raises(ValueError, match="Duplicate slug"):
            CorporaConfig.from_dicts([
                {"id": "a", "slug": "dup", "name": "A", "description": "",
                 "chunker": "paragraph", "documents": "a.md"},
                {"id": "b", "slug": "dup", "name": "B", "description": "",
                 "chunker": "paragraph", "documents": "b.md"},
            ])

    def test_duplicate_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate id"):
            CorporaConfig.from_dicts([
                {"id": "same", "slug": "a", "name": "A", "description": "",
                 "chunker": "paragraph", "documents": "a.md"},
                {"id": "same", "slug": "b", "name": "B", "description": "",
                 "chunker": "paragraph", "documents": "b.md"},
            ])


# ── Integration (real YAML) ──────────────────────────────────────────────────


class TestCorporaConfigFromYaml:
    def test_loads_real_corpora_yaml(self) -> None:
        """End-to-end: reads the actual corpora.yaml and resolves chunkers."""
        config = CorporaConfig()
        corpora = config.list()
        # The real file has at least one corpus
        assert len(corpora) >= 1

        first = corpora[0]
        assert first.slug is not None
        assert first.chunker is not None

        # Chunker is resolvable
        chunker = config.get_chunker(first.slug)
        assert chunker is not None
        assert hasattr(chunker, "chunk")

    def test_empty_list_when_yaml_missing(self, tmp_path) -> None:
        """Missing file returns empty list, doesn't crash."""
        missing = str(tmp_path / "nonexistent.yaml")
        config = CorporaConfig(yaml_path=missing)
        assert config.list() == []
