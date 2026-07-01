import { createSignal, type Component } from "solid-js";
import { useLocation, type RouteSectionProps } from "@solidjs/router";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { useCorpora } from "@/corpora/CorporaProvider";
import { createThemeSignal } from "@/theme/theme";
import { Header } from "./Header";
import { Sidebar } from "@/conversations/Sidebar";

import { triggerConversationSwitch } from "@/corpora/CorpusChatPage";

export const RootLayout: Component<RouteSectionProps> = (props) => {
  const [sidebarOpen, setSidebarOpen] = createSignal(false);
  const [theme, toggleTheme] = createThemeSignal();
  const store = useConversationStore();
  const corpora = useCorpora();
  const location = useLocation();

  const activeCorpusId = () => {
    const path = location.pathname;
    if (!path.startsWith("/corpora/")) return null;
    const slug = path.split("/corpora/")[1];
    if (!slug) return null;
    const corpus = corpora.resolveSlug(slug);
    return corpus?.id ?? null;
  };

  return (
    <div class="h-dvh flex flex-col">
      <Header
        sidebarOpen={sidebarOpen()}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
        theme={theme}
        onToggleTheme={toggleTheme}
        onNewConversation={() => {
          const corpusId = activeCorpusId();
          if (corpusId) store.createNew(corpusId);
        }}
      />

      <div class="flex flex-1 overflow-hidden">
        {activeCorpusId() && (
          <Sidebar
            conversations={store.conversations()}
            currentId={store.currentId()}
            activeCorpusId={activeCorpusId()!}
            onSelect={(id) => { store.switchTo(id); triggerConversationSwitch(id); }}
            onNew={() => store.createNew(activeCorpusId()!)}
            onDelete={(id) => {
              store.switchTo(id);
              store.removeCurrent();
            }}
            isOpen={sidebarOpen()}
            onClose={() => setSidebarOpen(false)}
          />
        )}

        <main class="flex-1 flex flex-col overflow-hidden">
          {props.children}
        </main>
      </div>
    </div>
  );
};
