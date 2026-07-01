import { describe, it, expect, vi, afterEach } from "vitest";
import { createRoot } from "solid-js";
import { createCorporaContext } from "@/corpora/CorporaContext";

const FAKE_CORPORA = [
  { id: "uuid-1", slug: "eu-ai-act", name: "EU AI Act", description: "The regulation" },
  { id: "uuid-2", slug: "gdpr", name: "GDPR", description: "Privacy law" },
];

function mockFetch(data: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

describe("CorporaContext", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches corpus list from GET /api/corpora on mount and exposes resolved corpora", async () => {
    const fetch = mockFetch(FAKE_CORPORA);

    let corpora!: ReturnType<typeof createCorporaContext>;
    createRoot(() => {
      corpora = createCorporaContext({ fetch });
    });

    expect(corpora.loading()).toBe(true);
    expect(corpora.error()).toBeNull();

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });

    expect(corpora.error()).toBeNull();
    expect(corpora.corpora()).toEqual(FAKE_CORPORA);
  });

  it("sets error state when fetch fails", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    let corpora!: ReturnType<typeof createCorporaContext>;
    createRoot(() => {
      corpora = createCorporaContext({ fetch });
    });

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });

    expect(corpora.error()).toBe("Failed to load knowledge bases");
    expect(corpora.corpora()).toEqual([]);
  });

  it("resolves slug to corpus", async () => {
    const fetch = mockFetch(FAKE_CORPORA);

    let corpora!: ReturnType<typeof createCorporaContext>;
    createRoot(() => {
      corpora = createCorporaContext({ fetch });
    });

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });

    expect(corpora.resolveSlug("eu-ai-act")).toEqual(FAKE_CORPORA[0]);
    expect(corpora.resolveSlug("nonexistent")).toBeUndefined();
  });

  it("resolves id to corpus", async () => {
    const fetch = mockFetch(FAKE_CORPORA);

    let corpora!: ReturnType<typeof createCorporaContext>;
    createRoot(() => {
      corpora = createCorporaContext({ fetch });
    });

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });

    expect(corpora.resolveId("uuid-1")).toEqual(FAKE_CORPORA[0]);
    expect(corpora.resolveId("bad-id")).toBeUndefined();
  });

  it("retries fetch when retry() is called after error", async () => {
    const failFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    const fetch = vi.fn().mockImplementationOnce(() => failFetch());

    let corpora!: ReturnType<typeof createCorporaContext>;
    createRoot(() => {
      corpora = createCorporaContext({ fetch });
    });

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });
    expect(corpora.error()).toBeTruthy();

    // Replace fetch implementation for retry
    fetch.mockImplementation(() => mockFetch(FAKE_CORPORA)());
    corpora.retry();

    expect(corpora.loading()).toBe(true);

    await vi.waitFor(() => {
      expect(corpora.loading()).toBe(false);
    });
    expect(corpora.error()).toBeNull();
    expect(corpora.corpora()).toEqual(FAKE_CORPORA);
  });
});
