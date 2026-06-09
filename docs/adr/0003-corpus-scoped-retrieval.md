# ADR-0003: Corpus-Scoped Retrieval with Stable UUIDs

Every chunk in pgvector carries a `corpus_id` (UUIDv4). All retrieval queries filter by it. Corpora have three identifiers: a stable `id` (UUIDv4, never changes), a mutable `slug` (route segment), and a `name` (display label). Slugs can be renamed — broken bookmarks produce a gentle explanatory page rather than a force-redirect.

This is a deliberate non-decision: cross-corpus retrieval, mid-conversation corpus switching, and blended queries are explicitly out of scope.

**Status:** accepted

**Considered options:**
- Slug-based retrieval: discarded — renaming a slug would corrupt existing data
- Single flat store: discarded — would require full-scan filtering

**Consequences:**
- Adding a corpus = `corpora.yaml` entry + document glob + seeding
- `GET /api/corpora` drives frontend routing and card display
