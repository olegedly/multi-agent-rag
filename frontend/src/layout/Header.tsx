import type { Component } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { useCorpora } from "@/corpora/CorporaProvider";

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  theme: () => "light" | "dark";
  onToggleTheme: () => void;
  onNewConversation: () => void;
}

export const Header: Component<HeaderProps> = (props) => {
  const location = useLocation();
  const corpora = useCorpora();

  // Determine if we're on a corpus route
  const isCorpusRoute = () => {
    const path = location.pathname;
    return path.startsWith("/corpora/");
  };

  const corpusName = () => {
    if (!isCorpusRoute()) return null;
    const slug = location.pathname.split("/corpora/")[1];
    if (!slug) return null;
    const corpus = corpora.resolveSlug(slug);
    return corpus?.name ?? null;
  };

  const title = () => {
    const name = corpusName();
    return name ? `Multi-Agent RAG: ${name}` : "Multi-Agent RAG";
  };

  return (
    <header class="flex items-center justify-between px-4 py-3 bg-(--header-bg) border-b border-(--border) shrink-0 z-40">
      <div class="flex items-center gap-3">
        {/* Hamburger — visible on mobile, only on corpus routes */}
        {isCorpusRoute() && (
          <button
            class="md:hidden p-2 text-(--text-primary) hover:bg-(--hover) rounded-lg transition-colors cursor-pointer"
            onClick={props.onToggleSidebar}
            title="Toggle sidebar"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
        )}

        {/* Title: links to / on corpus routes, plain text on landing */}
        {isCorpusRoute() ? (
          <A href="/" class="text-lg font-semibold text-(--text-primary) no-underline hover:underline">
            {title()}
          </A>
        ) : (
          <h1 class="text-lg font-semibold text-(--text-primary)">
            {title()}
          </h1>
        )}
      </div>

      <div class="flex items-center gap-2">
        {/* New conversation — visible on mobile, only on corpus routes */}
        {isCorpusRoute() && (
          <button
            class="md:hidden px-3 py-1 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors cursor-pointer"
            onClick={() => {
              props.onNewConversation();
              props.onToggleSidebar();
            }}
          >
            + New
          </button>
        )}

        {/* Theme toggle */}
        <button
          onClick={props.onToggleTheme}
          class="p-2 text-(--text-primary) hover:bg-(--hover) rounded-lg transition-colors cursor-pointer"
          title="Toggle theme"
        >
          {props.theme() === "dark" ? (
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                clip-rule="evenodd"
              />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  );
};
