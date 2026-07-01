import { describe, it, expect, beforeEach, vi } from "vitest";

// We need to set up DOM and localStorage before importing theme.ts
// because initTheme fires synchronously on import.
const ORIGINAL_DATA_THEME = document.documentElement.getAttribute("data-theme");

beforeEach(() => {
  localStorage.clear();
  // Restore any data-theme attribute that was set before this suite ran
  if (ORIGINAL_DATA_THEME) {
    document.documentElement.setAttribute("data-theme", ORIGINAL_DATA_THEME);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
});

describe("initTheme", () => {
  it("reads a stored theme from localStorage and sets data-theme", async () => {
    localStorage.setItem("theme", "light");

    const { initTheme } = await import("../theme");

    initTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("detects light from prefers-color-scheme when nothing is stored", async () => {
    localStorage.removeItem("theme");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === "(prefers-color-scheme: light)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    const { initTheme } = await import("../theme");
    initTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("detects dark from prefers-color-scheme when nothing is stored and no light preference", async () => {
    localStorage.removeItem("theme");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: "",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    const { initTheme } = await import("../theme");
    initTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("persists detected theme to localStorage when nothing was stored", async () => {
    localStorage.removeItem("theme");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === "(prefers-color-scheme: light)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    const { initTheme } = await import("../theme");
    initTheme();

    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("does NOT overwrite a previously stored theme", async () => {
    localStorage.setItem("theme", "dark");

    const { initTheme } = await import("../theme");
    initTheme();

    expect(localStorage.getItem("theme")).toBe("dark");
});
});

describe("createThemeSignal", () => {
  beforeEach(() => {
    // Restore matchMedia to jsdom default (mocked by some initTheme tests)
    delete (window as any).matchMedia;
  });

  it("reads initial theme from document data-theme attribute", async () => {
    document.documentElement.setAttribute("data-theme", "light");

    const { createThemeSignal } = await import("../theme");
    const [theme] = createThemeSignal();

    expect(theme()).toBe("light");
  });

  it("defaults to dark when no data-theme attribute is set", async () => {
    document.documentElement.removeAttribute("data-theme");

    const { createThemeSignal } = await import("../theme");
    const [theme] = createThemeSignal();

    expect(theme()).toBe("dark");
  });

  it("toggle flips from light to dark and updates DOM + localStorage", async () => {
    document.documentElement.setAttribute("data-theme", "light");

    const { createThemeSignal } = await import("../theme");
    const [theme, toggle] = createThemeSignal();

    expect(theme()).toBe("light");

    toggle();

    expect(theme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("toggle flips from dark to light", async () => {
    document.documentElement.setAttribute("data-theme", "dark");

    const { createThemeSignal } = await import("../theme");
    const [theme, toggle] = createThemeSignal();

    expect(theme()).toBe("dark");

    toggle();

    expect(theme()).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
  });
});
