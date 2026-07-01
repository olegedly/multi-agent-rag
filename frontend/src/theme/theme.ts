import { createSignal } from "solid-js";

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
  const getInitial = (): "light" | "dark" =>
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
