import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { Router, Route } from "@solidjs/router";
import { CorporaProvider } from "@/corpora/CorporaProvider";
import { LandingPage } from "@/corpora/LandingPage";

const FAKE_CORPORA = [
  { id: "uuid-1", slug: "eu-ai-act", name: "EU AI Act", description: "The regulation" },
];

function mockFetch(data: unknown) {
  return vi.fn<typeof globalThis.fetch>().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

function renderLanding(fetch: typeof globalThis.fetch) {
  return render(() => (
    <CorporaProvider fetch={fetch}>
      <Router root={(props) => props.children}>
        <Route path="/" component={LandingPage} />
      </Router>
    </CorporaProvider>
  ));
}

describe("LandingPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders product intro text", async () => {
    renderLanding(mockFetch(FAKE_CORPORA));
    expect(screen.getByText(/Multi-agent research assistant/)).toBeTruthy();
  });

  it("shows loading state while fetching", () => {
    // A fetch that never resolves
    const fetch = vi.fn().mockReturnValue(new Promise(() => {}));
    renderLanding(fetch as typeof globalThis.fetch);
    expect(screen.getByText("Loading knowledge bases...")).toBeTruthy();
  });

  it("shows error state when fetch fails", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue({ ok: false, status: 500 } as Response);
    renderLanding(fetch);
    await vi.waitFor(() => {
      expect(screen.getByText("Failed to load knowledge bases")).toBeTruthy();
    });
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("renders corpus cards from the fetched list", async () => {
    renderLanding(mockFetch(FAKE_CORPORA));
    await vi.waitFor(() => {
      expect(screen.getByText("EU AI Act")).toBeTruthy();
    });
    expect(screen.getByText("The regulation")).toBeTruthy();
  });

  it("renders a link to the corpus route per card", async () => {
    renderLanding(mockFetch(FAKE_CORPORA));
    await vi.waitFor(() => {
      const link = screen.getByText("EU AI Act").closest("a");
      expect(link?.getAttribute("href")).toBe("/corpora/eu-ai-act");
    });
  });

  it("shows empty state when no corpora available", async () => {
    const fetch = mockFetch([]);
    renderLanding(fetch);
    await vi.waitFor(() => {
      expect(screen.getByText("No knowledge bases available.")).toBeTruthy();
    });
  });
});
