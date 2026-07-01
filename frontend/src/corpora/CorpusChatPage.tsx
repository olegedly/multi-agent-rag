import { Show, For, createEffect, on, untrack, type Component } from "solid-js";
import { A, useParams } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { ChatView } from "@/chat/ChatView";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "@/chat/resilientFetch";
import { generateTitle } from "@/conversations/title";


/** Chat session — mounted per conversation via For's keyed lifecycle. */
const ConversationChat: Component<{ convId: string; corpusSlug: string }> = (props) => {
  const store = useConversationStore();
  const sseUrl = () => `/api/chat/${props.corpusSlug}`;


  const chat = useChat({
    id: `chat-${props.convId}`,
    initialMessages: store.getCurrentMessages(),
    get connection() {
      return fetchServerSentEvents(sseUrl(), {
        fetchClient: resilientFetch,
      });
    },
  });

  // Persist messages when they change AFTER initial mount
  // (initial messages come from the store already persisted; re-saving
  // bumps updatedAt and re-sorts the sidebar for no reason)
  let initial = true;
  createEffect(() => {
    const msgs = chat.messages();
    if (initial) { initial = false; return; }
    if (msgs.length > 0) {
      untrack(() => store.saveCurrentMessages(msgs));
    }
  });

  // Derive title when first user message appears
  createEffect(() => {
    const msgs = chat.messages();
    if (msgs.length > 0) {
      const title = deriveTitle(msgs);
      if (title) {
        untrack(() => store.updateCurrentTitle(title));
      }
    }
  });

  const handleSend = (text: string) => {
    const msgs = chat.messages();
    if (msgs.length === 0) store.updateCurrentTitle(generateTitle(text));
    chat.sendMessage(text);
  };

  return (
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
  );
};

export const CorpusChatPage: Component = () => {
  const params = useParams();
  const corpora = useCorpora();
  const store = useConversationStore();

  const corpus = () => corpora.resolveSlug(params.slug);
  const isUnknown = () => !corpora.loading() && !corpus();
  const isLoading = () => corpora.loading();

  // On initial corpus mount: load most recent conversation
  createEffect(
    on(
      () => corpus(),
      (c) => {
        if (!c) return;
        const convs = store.conversations().filter((conv) => conv.corpusId === c.id);
        if (convs.length > 0) store.switchTo(convs[0].id);
        else store.createNew(c.id);
      },
    ),
  );


  return (
    <>
      <Show when={isLoading()}>
        <div class="flex items-center justify-center h-full"><p class="text-(--text-secondary)">Loading...</p></div>
      </Show>
      <Show when={isUnknown()}>
        <div class="flex flex-col items-center justify-center h-full gap-4 px-6">
          <p class="text-(--text-secondary) text-center">This knowledge base doesn't exist or its address has changed.</p>
          <A href="/" class="px-4 py-2 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors no-underline">Browse available knowledge bases</A>
        </div>
      </Show>
      <Show when={corpus() && !isLoading()}>
        {/* For keys by identity — when currentId() changes it unmounts old
            ConversationChat and mounts a fresh one with initialMessages. */}
        <For each={store.currentId() ? [store.currentId()] : []}>
          {(convId) => (
            <ConversationChat convId={convId} corpusSlug={params.slug} />
          )}
        </For>
      </Show>
    </>
  );
};

function deriveTitle(msgs: any[]): string | null {
  const firstUser = msgs.find((m: any) => m.role === "user");
  if (!firstUser) return null;
  const text = firstUser.parts.filter((p: any) => p.type === "text").map((p: any) => p.content).join(" ");
  if (text.length === 0) return null;
  return generateTitle(text);
}
