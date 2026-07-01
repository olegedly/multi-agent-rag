# Grill Me Results

Generated: 2026-07-01T10:16:16.441Z

## Plan

let's work on github issue 26 (you have `gh`). what's not clear?

## Shared Understanding

Issue #26 — Frontend routing, landing page, and corpus-aware conversations. Design finalized across 19 decisions. Core architecture: domain-based structure (app/, theme/, layout/, corpora/, chat/, conversations/), history-based routing with @solidjs/router, CorporaContext for cached corpus list, per-route useChatSession, ConversationStoreContext for persistence, Conversation model gains corpusId + updatedAt, sidebar self-filters by corpus, legacy conversation migration to first corpus UUID. Tests written TDD under domain directories.

## Questions and Answers

### 1. How should the current hardcoded chat endpoint (/api/chat/eu-ai-act) be parameterized by corpus?

**Recommended answer:** The useChatStore should accept a corpusSlug parameter. When the route changes to /corpora/:slug, the chat store reconnects to /api/chat/{slug}. The corpus list from GET /api/corpora provides the slug→UUID mapping.

**User answer:** _(not recorded)_

**Status:** open

### 2. How should the corpus collection (fetched from GET /api/corpora) be managed between routes?

**Recommended answer:** Create a CorporaContext at the App level wrapping Router. Fetches GET /api/corpora on mount once, stores in a signal, exposes resolveSlug(slug) helper. Shared across all routes without re-fetching.

**User answer:** _(not recorded)_

**Status:** open

### 3. Should @solidjs/router use hash-based or history-based routing?

**Recommended answer:** History-based routing (createBrowserRouter/Router). The Caddyfile already has try_files {path} /index.html for SPA fallback, so clean URLs like /corpora/eu-ai-act work without configuration changes.

**User answer:** _(not recorded)_

**Status:** open

### 4. Where should useChatStore live in the route hierarchy?

**Recommended answer:** Keep useChatStore at the App level (Option B) but make it accept a corpusSlug() signal. When the slug changes via route navigation, the chat store internally disconnects old SSE, persists current messages, clears, and connects to the new /api/chat/{slug} endpoint. This avoids remounting the entire chat UI and keeps the sidebar accessible to conversations from all corpora.

**User answer:** _(not recorded)_

**Status:** open

### 5. How should existing persisted conversations (without corpusId) be handled for backwards compatibility?

**Recommended answer:** On deserialization in the store, conversations without a corpusId should default to the first corpus's UUID (fetched from GET /api/corpora). This keeps legacy conversations visible under one corpus. If no corpora exist (unlikely, but defensive), fall back to an empty-string sentinel that's treated as "show in all views."

**User answer:** _(not recorded)_

**Status:** open

### 6. How should existing persisted conversations (without corpusId) be handled for backwards compatibility?

**Recommended answer:** On deserialization in the store, conversations without a corpusId should default to the first corpus's UUID (fetched from GET /api/corpora). This keeps legacy conversations visible under one corpus. If no corpora exist (unlikely, but defensive), fall back to an empty-string sentinel that's treated as "show in all views."

**User answer:** Assign them to the first corpus's UUID and persist that edit.

**Status:** resolved

### 7. What should the Conversation model changes look like exactly?

**Recommended answer:** Add corpusId: string as a required field to the Conversation interface. Update createConversation() to accept a corpusId parameter. Add migration logic in createConversationStore() that assigns first corpus UUID to any loaded conversation missing corpusId, then persists the fix.

**User answer:** _(not recorded)_

**Status:** open

### 8. What should the Conversation model changes look like exactly?

**Recommended answer:** Add corpusId: string as a required field. Add migration in createConversationStore() that assigns first corpus UUID to conversations loaded without corpusId. Update createConversation() to accept a corpusId parameter.

**User answer:** Yes. corpusId is required; migration assigns first corpus UUID.

**Status:** resolved

### 9. How should the sidebar filter conversations by corpus?

**Recommended answer:** Sidebar receives activeCorpusId as a prop and filters the conversation list via the existing enriched memo before rendering. A small header inside the sidebar shows the current corpus name. This keeps filtering self-contained inside the sidebar.

**User answer:** _(not recorded)_

**Status:** open

### 10. How should the sidebar filter conversations by corpus?

**Recommended answer:** Sidebar receives activeCorpusId as a prop and filters internally. No corpus name in sidebar — instead extend the page header to "Multi-Agent RAG: {corpus name}" on corpus routes. Landing page shows just "Multi-Agent RAG".

**User answer:** Filter in sidebar. No corpus name in sidebar — extend the page header to "Multi-Agent RAG: EU AI Act" style instead.

**Status:** resolved

**Notes:** User clarified: sidebar filters internally via activeCorpusId prop. No corpus name in sidebar — instead extend the page header to "Multi-Agent RAG: {corpus name}" on corpus routes. Landing page shows just "Multi-Agent RAG".

### 11. How should the route and layout structure be organized?

**Recommended answer:** Shared layout pattern (Option A): Router wraps a RootLayout with header + sidebar + Outlet. Landing page and corpus chat page are child routes. Sidebar and header persist across navigations. Header title updates reactively based on current route/corpus.

**User answer:** _(not recorded)_

**Status:** open

### 12. How should the route and layout structure be organized?

**Recommended answer:** Shared layout pattern: Router wraps a RootLayout with header + sidebar + {props.children}. Landing page and corpus chat page are child routes. Sidebar and header persist across navigations. Header title updates reactively.

**User answer:** Agreed — shared layout with Router root prop. No outlet, just props.children.

**Status:** resolved

### 13. What should the landing page look like, and should the sidebar be visible on it?

**Recommended answer:** Centered layout with product intro text + grid of corpus cards (name + description). Loading spinner, error+retry, empty state. Sidebar visible but showing a "Select a knowledge base to begin" placeholder instead of the conversation list, since there's no active corpus.

**User answer:** _(not recorded)_

**Status:** open

### 14. What should the landing page look like, and should the sidebar be visible on it?

**Recommended answer:** Centered layout with product intro text + grid of corpus cards. Loading/error/empty states included.

**User answer:** Option A — sidebar hidden on landing page. Full-width centered content.

**Status:** resolved

### 15. How should the header change across routes?

**Recommended answer:** RootLayout reads current path via useLocation(). Landing page header: just title. Corpus page header: back link + title "Multi-Agent RAG: {name}" + hamburger/new (mobile) + theme toggle. Theme toggle always visible on both routes.

**User answer:** _(not recorded)_

**Status:** open

**Notes:** Header lives in RootLayout (moved out of App.tsx). Conditionally renders elements based on current route. Back link on corpus page navigates to /. Theme toggle always visible.

### 16. How should the header change across routes?

**Recommended answer:** RootLayout reads current path via useLocation(). Landing page: just "Multi-Agent RAG" (plain). Corpus page: "Multi-Agent RAG" is a link to / + hamburger/new (mobile) + theme toggle.

**User answer:** The "Multi-Agent RAG" title is the link to / on corpus routes. Landing page shows plain text.

**Status:** resolved

**Notes:** The "Multi-Agent RAG" title in the header acts as a link to / only on corpus routes. Landing page header title is plain text (no link needed).

### 17. What happens on /corpora/:slug when the slug is unknown?

**Recommended answer:** Corpus route resolves slug against cached corpus list via CorporaContext. If not found, render in-place error message + "Browse available knowledge bases" button (links to /). Sidebar and header remain visible.

**User answer:** _(not recorded)_

**Status:** open

### 18. What happens on /corpora/:slug when the slug is unknown?

**Recommended answer:** Resolve slug against cached corpus list. Not found = in-place error message + "Browse available knowledge bases" <A href="/"> button. Sidebar and header remain visible.

**User answer:** Agreed. Use the SolidJS A component for links (client-side navigation).

**Status:** resolved

**Notes:** Use <A> component from @solidjs/router (SolidJS's client-side navigation link). Not yet installed — will add as dependency.

### 19. How does the SSE connection/chat endpoint get parameterized by corpus slug?

**Recommended answer:** Parameterize useChatStore with a corpusSlug() getter. Create a createEffect that watches the slug, saves current messages, and reconnects the SSE to /api/chat/{slug} on change. This keeps the store at App level while being reactive to route changes.

**User answer:** _(not recorded)_

**Status:** open

### 20. How does the SSE connection/chat endpoint get parameterized by corpus slug?

**Recommended answer:** Let the corpus route component own the chat instance. useChat is instantiated inside /corpora/:slug with the correct URL from route params. App keeps only createConversationStore for persistence. Clean mount/unmount lifecycle.

**User answer:** Yes — lift the restriction. Per-route chat instantiation.

**Status:** resolved

**Notes:** Per-route chat instantiation. UseChat lives in the corpus route component, receives the correct slug from route params. App level keeps only createConversationStore for persistence + sidebar access.

### 21. How does CorpusChatPage access the conversation store?

**Recommended answer:** Create a ConversationStoreContext. App wraps Router with the provider. CorpusChatPage and Sidebar consume it via a useConversationStore() hook. Cleaner than prop-drilling through Route component.

**User answer:** _(not recorded)_

**Status:** open

### 22. How does the New conversation button interact with corpus scoping?

**Recommended answer:** Sidebar's onNew calls createConversation(corpusId) with the active corpus UUID. The per-route chat component resets useChat state to the new empty conversation. Header's +New (mobile) does the same.

**User answer:** _(not recorded)_

**Status:** open

### 23. How does the New conversation button interact with corpus scoping?

**Recommended answer:** Sidebar's onNew: save current → createNew(corpusId) → clear useChat → empty fresh input ready. Same flow as current just with corpusId scoping.

**User answer:** Yes — persist current, then create new in the active corpus. Standard flow.

**Status:** resolved

**Notes:** New conversation: persist current → createNew(corpusId) in store → clear useChat → ready for input. Same as current flow + corpusId parameter.

### 24. What new files should be created and where?

**Recommended answer:** Create RootLayout.tsx (shared layout), LandingPage.tsx (corpus cards), CorpusChatPage.tsx (chat route with slug resolution), CorporaContext.tsx (corpus list context), ConversationStoreContext.tsx (store context), Header.tsx (extracted from App). conversations/ stays as-is.

**User answer:** _(not recorded)_

**Status:** open

**Notes:** New files: RootLayout.tsx, LandingPage.tsx, CorpusChatPage.tsx, CorporaContext.tsx, ConversationStoreContext.tsx, Header.tsx. Existing conversations/ stays mostly unchanged.

### 25. What new files should be created and where?

**Recommended answer:** src/app/ (App, entry), theme/ (theme.ts), layout/ (RootLayout, Header), corpora/ (LandingPage, CorporaContext), chat/ (ChatInput, ChatView, MessageList, MessagePartRenderer, CollapsibleSection, collapse, formatToolResult, groupParts, toolResultTracker, resilientFetch, useChatStore), conversations/ (store, Sidebar, title, ConversationStoreContext).

**User answer:** Yes, use this domain-based structure.

**Status:** resolved

**Notes:** Domain-based: app/, theme/, layout/, corpora/, chat/, conversations/. The existing conversations/ contents (store, sidebar, title, ConversationStoreContext) stay in conversations/ with the test files inside the domain dirs.

### 26. Should we configure a Vite path alias (@/) for clean imports?

**Recommended answer:** Yes. Add @/ → src/ in vite.config.ts (resolve.alias) and tsconfig.json (paths). Keeps imports clean across the new domain directories and makes future refactors easier.

**User answer:** _(not recorded)_

**Status:** open

**Notes:** Vite alias @/ -> src/ for clean cross-domain imports. Requires updating vite.config.ts and tsconfig.json.

### 27. Should we configure a Vite path alias (@/) for clean imports?

**Recommended answer:** Yes. Add @/ → src/ in vite.config.ts (resolve.alias) and tsconfig.json (paths).

**User answer:** Yes.

**Status:** resolved

**Notes:** Add @/ alias in vite.config.ts resolve.alias and tsconfig.json compilerOptions.paths.

### 28. What tests should be written for the new functionality?

**Recommended answer:** 9 tests: landing card render, loading, error, slug resolution, unknown slug, sidebar filtering, new convo corpusId, legacy migration, header update on navigation. Tests live in __tests__/ within each domain dir.

**User answer:** _(not recorded)_

**Status:** open

**Notes:** 7+ tests per AC. Proposing 9 tests across all new functionality.

### 29. What tests should be written for the new functionality?

**Recommended answer:** Target roughly 9 tests covering the AC. Written TDD during implementation.

**User answer:** Guideline accepted. TDD during implementation will determine the exact test suite.

**Status:** resolved

**Notes:** Tests will be written TDD-style during implementation. The proposed 9-test scope is a guideline, not a contract.

### 30. Should existing test/setup files move into the new domain structure?

**Recommended answer:** Move theme.test.ts to theme/__tests__/. Keep __testSetup__/setup.ts where it is (referenced by vitest.config.ts).

**User answer:** _(not recorded)_

**Status:** open

**Notes:** Existing theme.test.ts at src/__tests__/ and setup.ts at src/__testSetup__/ need decisions about relocation.

### 31. Should existing test/setup files move into the new domain structure?

**Recommended answer:** Move setup.ts to app/__tests__/setup.ts, theme.test.ts to theme/__tests__/, and distribute existing conversation tests into their domain __tests__/ dirs. Update vitest.config.ts setupFiles path accordingly.

**User answer:** Yes — organize under new domains, update vitest config path.

**Status:** resolved

**Notes:** setup.ts -> app/__tests__/setup.ts, theme.test.ts -> theme/__tests__/, existing conversation tests move into their domain's __tests__/ dir.

### 32. What does the corpus route chat component look like — a lightweight useChatSession hook, or direct wiring?

**Recommended answer:** Lightweight useChatSession(corpusSlug, conversationStore) hook in chat/ that wraps TanStack useChat with agent name tracking and auto-save. Conversation store stays separate in conversations/ via context.

**User answer:** _(not recorded)_

**Status:** open

**Notes:** Do we extract a lightweight useChatSession hook in chat/, or wire things directly in CorpusChatPage?

### 33. What does the corpus route chat component look like?

**Recommended answer:** Lightweight useChatSession(corpusSlug, conversationStore) hook in chat/ wrapping TanStack useChat with agent name tracking and auto-save.

**User answer:** Agreed.

**Status:** resolved

**Notes:** Lightweight useChatSession(corpusSlug, conversationStore) in chat/. Handles SSE, agent names, auto-save.

### 34. When navigating to a corpus route with multiple conversations, which one loads?

**Recommended answer:** Per-corpus last-opened tracking. Extend persistence to store {corpusId -> lastConversationId}. On navigation, load that conversation. Fall back to most recent if no record exists for the corpus.

**User answer:** _(not recorded)_

**Status:** open

### 35. When navigating to a corpus route with multiple conversations, which one loads?

**Recommended answer:** Most recently updated conversation (by updatedAt field). Sidebar sorts by updatedAt descending. No per-corpus lastOpened needed — the corpus filter + updatedAt sort is sufficient.

**User answer:** The conversation with the most recent last message. Sidebar also sorts by that criterion. Adds updatedAt field to Conversation model.

**Status:** resolved

**Notes:** Conversation gets updatedAt field. Sorting and default selection use updatedAt descending. Existing createdAt stays for reference.

### 36. Should the "New conversation" de-duplication logic be scoped per-corpus?

**Recommended answer:** Yes. De-duplication should only match conversations with the same corpusId + title "New conversation" + empty messages. Otherwise, switching corpora and hitting +New would incorrectly switch to an empty convo in a different corpus.

**User answer:** _(not recorded)_

**Status:** open

## Agreed Decisions

- Chat endpoint is parameterized by corpus slug — per-route useChatSession hook
- Corpus list fetched once via CorporaContext at App level, shared across all routes
- History-based routing (@solidjs/router) — Caddyfile already has SPA fallback
- createConversationStore lives at App level via context; chat instantiation belongs to the route
- Legacy conversations without corpusId are migrated to first corpus UUID on deserialization
- Conversation model gains required corpusId: string + updatedAt: number
- Sidebar self-filters conversations by activeCorpusId prop, sorted by updatedAt descending
- Header shows 'Multi-Agent RAG' on landing page, 'Multi-Agent RAG: {name}' on corpus route — title links to /
- Shared RootLayout via Router root prop — sidebar and header persist across navigations
- Landing page: no sidebar, centered product intro + corpus cards grid + loading/error states
- Unknown slug renders in-place error message + Browse button using <A> component
- New conversation: persist current → createNew(corpusId) with per-corpus de-duplication → fresh chat
- ConversationStore accessed via context hook (useConversationStore)
- Domain-based directory structure: app/, theme/, layout/, corpora/, chat/, conversations/
- @/ Vite alias configured for clean imports
- Tests written TDD under domain __tests__/ subdirectories, vitest config updated
- useChatSession(corpusSlug, conversationStore) lightweight hook in chat/
- New convo de-duplication scoped to same corpusId
- No corpus name in sidebar — corpus identity shown only in page header

## Open Risks

- TanStack useChat/useChatSession hook compatibility with dynamic URL changes per-route — need to verify API during implementation
- @solidjs/router v0.10+ API specifics (Router root prop, {props.children} vs Outlet pattern) — package not yet installed, API surface needs verification
- CorpusContext fetch timing vs Router mount — if corpora not yet loaded when /corpora/:slug renders, need loading gate
- LocalStorage migration of existing conversations to add corpusId — deployed users may have stale data
- UpdatedAt field requires changes to existing save paths in useChatStore — all conversation saves must set updatedAt

## Next Decision Needed

Implementation order: (1) install @solidjs/router, configure Vite alias + tsconfig, (2) create domain directories + move existing files, (3) implement CorpusContext, (4) implement ConversationStoreContext + corpusId + updatedAt migration, (5) implement RootLayout + routing in App, (6) implement LandingPage, (7) implement CorpusChatPage + useChatSession, (8) wire sidebar filtering, (9) write TDD tests at each step.
