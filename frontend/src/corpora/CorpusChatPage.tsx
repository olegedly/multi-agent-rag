import { Show, createEffect, createContext, useContext, on, type Component, type JSX } from "solid-js";
import { A, useParams } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { ChatView } from "@/chat/ChatView";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "@/chat/resilientFetch";
import { generateTitle } from "@/conversations/title";

// Module-level switch: set by RootLayout, consumed synchronously by CorpusChatPage.
// Using a non-reactive slot so the switch logic runs outside SolidJS's batch.
let _onSwitch: ((id: string) => void) | null = null;
export function setConversationSwitcher(fn: ((id: string) => void) | null) {
  _onSwitch = fn;
}
export function triggerConversationSwitch(id: string) {
  _onSwitch?.(id);
}

export const CorpusChatPage: Component = () => {
  const params = useParams();
  const corpora = useCorpora();
  const store = useConversationStore();

  const corpus = () => corpora.resolveSlug(params.slug);
  const isUnknown = () => !corpora.loading() && !corpus();
  const isLoading = () => corpora.loading();

  const sseUrl = () => `/api/chat/${params.slug}`;

  const chat = useChat({
    get connection() {
      return fetchServerSentEvents(sseUrl(), {
        fetchClient: resilientFetch,
      });
    },
  });

  // On initial corpus mount: load most recent conversation for this corpus
  createEffect(
    on(
      () => corpus(),
      (c) => {
        if (!c) return;
        const convs = store.conversations().filter((conv) => conv.corpusId === c.id);
        if (convs.length > 0) {
          store.switchTo(convs[0].id);
          const msgs = store.getCurrentMessages();
          if (msgs.length > 0) chat.setMessages(msgs);
        } else {
          store.createNew(c.id);
        }
      },
    ),
  );

  // Register the switch handler. This runs synchronously from sidebar clicks.
  createEffect(() => {
    setConversationSwitcher((id: string) => {
      if (id === store.currentId()) return;
      const currentMsgs = chat.messages();
      if (currentMsgs.length > 0) {
        store.saveCurrentMessages(currentMsgs);
      }
      if (chat.isLoading()) chat.stop();
      chat.clear();
      store.switchTo(id);
      const msgs = store.getCurrentMessages();
      chat.setMessages(msgs);
    });
    return () => setConversationSwitcher(null);
  });

  const handleSend = (text: string) => {
    const msgs = chat.messages();
    if (msgs.length === 0) {
      store.updateCurrentTitle(generateTitle(text));
    }
    chat.sendMessage(text);
  };

  return (
    <>
      <Show when={isLoading()}>
        <div class="flex items-center justify-center h-full">
          <p class="text-(--text-secondary)">Loading...</p>
        </div>
      </Show>

      <Show when={isUnknown()}>
        <div class="flex flex-col items-center justify-center h-full gap-4 px-6">
          <p class="text-(--text-secondary) text-center">
            This knowledge base doesn't exist or its address has changed.
          </p>
          <A
            href="/"
            class="px-4 py-2 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors no-underline"
          >
            Browse available knowledge bases
          </A>
        </div>
      </Show>

      <Show when={corpus() && !isLoading()}>
        <ChatView
          messages={chat.messages}
          isLoading={chat.isLoading()}
          error={chat.error()?.message ?? null}
          storageError={store.storageError()}
          agentNameMap={{}}
          onSend={handleSend}
          onStop={() => chat.stop()}
          onDismissStorageError={() => store.setStorageError(null)}
          focusTick={0}
        />
      </Show>
    </>
  );
};
