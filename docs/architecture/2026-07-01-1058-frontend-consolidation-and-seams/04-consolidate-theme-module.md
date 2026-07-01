# Consolidate theme management behind one module

## Files involved

`frontend/src/index.tsx`, `frontend/src/App.tsx`, `frontend/src/theme.css`, `frontend/src/index.css`

## Problem

Theme initialization logic is duplicated across `index.tsx` (IIFE for FOUC prevention) and `App.tsx` (component-level signal + toggle) — two callers with the same logic, no single module.

## Topology (before)

```
index.tsx
  └─ (function initTheme() { ... })  IIFE — duplicates getInitialTheme

App.tsx
  └─ getInitialTheme()               reads localStorage, prefers-color-scheme
  └─ toggleTheme()                   writes localStorage, sets data-theme attr
  └─ <header> inline theme button
```

`getInitialTheme()` in `App.tsx` re-reads `localStorage.getItem("theme")` and `window.matchMedia("(prefers-color-scheme: light)")` — the same logic the IIFE in `index.tsx` ran 50ms earlier. There is no shared interface; the toggle side-effect knows about `localStorage.setItem` and `document.documentElement.setAttribute` directly.

## Solution

Create a single `theme.ts` module with `initTheme()` (side-effect for FOUC) and `createThemeSignal()` (reactive state + toggle), consumed by both entry points.

## Topology (after)

```
theme.ts
  ├─ initTheme(): void              ← runs synchronously on import, sets data-theme
  ├─ createThemeSignal() → [theme, toggle]
  │     └─ reads init state by checking DOM (single source of truth)
  │
  ├─ imported by index.tsx           ← initTheme() fires on import
  └─ imported by App.tsx             ← createThemeSignal() provides component state

CSS stays in theme.css (unchanged)
```

`initTheme()` is the IIFE logic extracted. `createThemeSignal()` reads the current `data-theme` attribute instead of re-running the detection logic.

## Interface design options

### Option A: Module with side-effect on import + exportable hook

```typescript
// theme.ts
const THEME_KEY = "theme";

function detectTheme(): "light" | "dark" {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) return "light";
  return "dark";
}

export function initTheme(): void {
  const t = detectTheme();
  document.documentElement.setAttribute("data-theme", t);
  if (!localStorage.getItem(THEME_KEY)) {
    localStorage.setItem(THEME_KEY, t);
  }
}

export function createThemeSignal() {
  const getInitial = () =>
    (document.documentElement.getAttribute("data-theme") as "light" | "dark") ?? "dark";
  const [theme, setTheme] = createSignal(getInitial());

  const toggle = () => {
    const next = theme() === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(THEME_KEY, next);
  };

  return [theme, toggle] as const;
}
```

**What's hidden:** The `detectTheme` logic lives in one place. `App.tsx` no longer reads `localStorage` or `matchMedia`.

### Option B: Reactive effect that syncs the attribute

```typescript
export function createThemeSignal() {
  const [theme, setTheme] = createSignal(
    (document.documentElement.getAttribute("data-theme") as "light" | "dark") ?? "dark"
  );

  createEffect(() => {
    const t = theme();
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  });

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return [theme, toggle] as const;
}
```

**Trade-offs:** Effect-based sync means the attribute write is deferred to the next microtask. The current code writes immediately in `toggleTheme()`. For the theme toggle button, the delay is imperceptible, but for `initTheme()` it matters — the IIFE must run synchronously before the first paint. So `initTheme()` stays imperative regardless.

### Recommendation

**Option A.** Keep the imperative sync for FOUC prevention. `createThemeSignal()` returns a `[theme, toggle]` tuple that replaces the ad-hoc `getInitialTheme()` + `toggleTheme` closure in `App.tsx`.

## Deepening strategy

- **Dependency category:** In-process. All callers are in the same browser context.
- **Seam placement:** `theme.ts` is the seam. The rest of the app calls `createThemeSignal()` and never touches `localStorage` or `data-theme` directly.
- **Adapters:** None needed. The seam is for *locality*, not substitutability.
- **Testing:** The existing tests don't exercise theme toggling. A new `theme.test.ts` tests `initTheme` with localStorage mocks and `createThemeSignal` with a controlled DOM.

## Benefits

- **Locality:** theme detection no longer duplicated in two files
- **Leverage:** one `createThemeSignal()` replaces two ad-hoc functions in App.tsx
- **Delete duplication:** `getInitialTheme()` and the IIFE body converge
- **Testable:** theme logic no longer lives inside a component's closure

## Recommendation strength

**Strong**

(No ADR conflicts. Theme architecture wasn't discussed in any existing ADR.)
