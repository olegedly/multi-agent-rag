import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { MemoryRouter, Route } from "@solidjs/router";
import { createMemoryHistory } from "@solidjs/router";
import { CorporaProvider } from "@/corpora/CorporaProvider";
import { ConversationStoreProvider } from "@/conversations/ConversationStoreProvider";
import { CorpusChatPage } from "@/corpora/CorpusChatPage";

const FAKE_CORPORA = [
  { id: "uuid-1", slug: "eu-ai-act", name: "EU AI Act", description: "The regulation" },
];

function mockFetch(data: unknown) {
  return vi.fn<typeof globalThis.fetch>().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

function renderCorpusPage(slug: string, fetch: typeof globalThis.fetch) {
  const history = createMemoryHistory();
  history.set({ value: `/corpora/${slug}`, replace: true });

  return render(() => (
    <CorporaProvider fetch={fetch}>
      <ConversationStoreProvider defaultCorpusId="uuid-1">
        <MemoryRouter root={(props) => props.children} history={history}>
          <Route path="/corpora/:slug" component={CorpusChatPage} />
        </MemoryRouter>
      </ConversationStoreProvider>
    </CorporaProvider>
  ));
}

describe("CorpusChatPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading while corpora are being fetched", () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockReturnValue(new Promise(() => {}));
    renderCorpusPage("eu-ai-act", fetch);
    expect(screen.getByText("Loading...")).toBeTruthy();
  });

  it("shows unknown slug error when corpus slug is not found", async () => {
    const fetch = mockFetch(FAKE_CORPORA);
    renderCorpusPage("bad-slug", fetch);
    await vi.waitFor(() => {
      expect(
        screen.getByText("This knowledge base doesn't exist or its address has changed."),
      ).toBeTruthy();
    });
  });

  it("shows Browse button linking to / for unknown slug", async () => {
    const fetch = mockFetch(FAKE_CORPORA);
    renderCorpusPage("bad-slug", fetch);
    await vi.waitFor(() => {
      const btn = screen.getByText("Browse available knowledge bases");
      expect(btn).toBeTruthy();
      expect(btn.closest("a")?.getAttribute("href")).toBe("/");
    });
  });

  it("shows chat view for a known corpus", async () => {
    const fetch = mockFetch(FAKE_CORPORA);
    renderCorpusPage("eu-ai-act", fetch);
    await vi.waitFor(() => {
      expect(screen.getByPlaceholderText("Type your message...")).toBeTruthy();
    });
  });
});
