import { createSignal } from "solid-js";
import { useChatStore } from "./conversations/useChatStore";
import { Sidebar } from "./conversations/Sidebar";
import { ChatView } from "./conversations/ChatView";

const App = () => {
  const [sidebarOpen, setSidebarOpen] = createSignal(false);
  const [theme, setTheme] = createSignal(getInitialTheme());

  const chat = useChatStore();

  const toggleTheme = () => {
    const next = theme() === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  };

  return (
    <div class="h-dvh flex flex-col">
      {/* Header */}
      <header class="flex items-center justify-between px-4 py-3 bg-(--header-bg) border-b border-(--border) shrink-0 z-40">
        <div class="flex items-center gap-3">
          {/* Hamburger — visible on mobile */}
          <button
            class="md:hidden p-2 text-(--text-primary) hover:bg-(--hover) rounded-lg transition-colors cursor-pointer"
            onClick={() => setSidebarOpen(!sidebarOpen())}
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

          <h1 class="text-lg font-semibold text-(--text-primary)">
            Multi-Agent RAG
          </h1>
        </div>

        <div class="flex items-center gap-2">
          {/* New conversation — visible on mobile */}
          <button
            class="md:hidden px-3 py-1 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors cursor-pointer"
            onClick={() => {
              chat.createNew();
              setSidebarOpen(false);
            }}
          >
            + New
          </button>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            class="p-2 text-(--text-primary) hover:bg-(--hover) rounded-lg transition-colors cursor-pointer"
            title="Toggle theme"
          >
            {theme() === "dark" ? (
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

      {/* Body: sidebar + chat */}
      <div class="flex flex-1 overflow-hidden">
        <Sidebar
          conversations={chat.conversations()}
          currentId={chat.currentId()}
          onSelect={(id) => chat.switchTo(id)}
          onNew={() => chat.createNew()}
          onDelete={(id) => {
            chat.switchTo(id);
            chat.deleteCurrent();
          }}
          isOpen={sidebarOpen()}
          onClose={() => setSidebarOpen(false)}
        />

        <main class="flex-1 flex flex-col overflow-hidden">
          <ChatView
            messages={chat.messages}
            isLoading={chat.isLoading()}
            error={chat.error()}
            storageError={chat.storageError()}
            onSend={(text) => chat.sendMessage(text)}
            onStop={() => chat.stop()}
            onDismissStorageError={() => chat.dismissStorageError()}
          />
        </main>
      </div>
    </div>
  );
};

function getInitialTheme(): "light" | "dark" {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  if (
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
  ) {
    return "light";
  }
  return "dark";
}

export default App;
