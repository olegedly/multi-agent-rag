import { Show, createEffect, type Component } from "solid-js";
import { A, useParams, useNavigate } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { ChatView } from "@/chat/ChatView";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "@/chat/resilientFetch";
import { generateTitle } from "@/conversations/title";

export const CorpusChatPage: Component = () => {
  const params = useParams();
  const corpora = useCorpora();
  const store = useConversationStore();

  const corpus = () => corpora.resolveSlug(params.slug);
  const isUnknown = () => !corpora.loading() && !corpus();
  const isLoading = () => corpora.loading();

  // SSE connection URL — depends on slug
  const sseUrl = () => `/api/chat/${params.slug}`;

  const chat = useChat({
    get connection() {
      return fetchServerSentEvents(sseUrl(), {
        fetchClient: resilientFetch,
      });
    },
  });

  // When entering a known corpus, load the most recent conversation for it
  createEffect(() => {
    const c = corpus();
    if (!c) return;
    const convs = store.conversations().filter((conv) => conv.corpusId === c.id);
    if (convs.length > 0) {
      const mostRecent = convs[0]; // already sorted by updatedAt desc
      store.switchTo(mostRecent.id);
      const msgs = store.getCurrentMessages();
      if (msgs.length > 0) {
        chat.setMessages(msgs);
      }
    } else {
      // No conversations yet — create one
      store.createNew(c.id);
    }
  });

  // Save messages when navigating away
  const saveCurrent = () => {
    const msgs = chat.messages();
    if (msgs.length > 0) {
      const title = deriveTitle(msgs);
      store.saveCurrentMessages(msgs);
      if (title) {
        store.updateCurrentTitle(title);
      }
    }
  };

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

function deriveTitle(msgs: any[]): string | null {
  const firstUser = msgs.find((m: any) => m.role === "user");
  if (!firstUser) return null;
  const text = firstUser.parts
    .filter((p: any) => p.type === "text")
    .map((p: any) => p.content)
    .join(" ");
  if (text.length === 0) return null;
  return generateTitle(text);
}
