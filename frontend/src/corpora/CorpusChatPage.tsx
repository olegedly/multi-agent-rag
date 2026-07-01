import { Show, createEffect, createSignal, on, type Component } from "solid-js";
import { A, useParams } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { ChatView } from "@/chat/ChatView";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "@/chat/resilientFetch";
import { generateTitle } from "@/conversations/title";

/** Chat session — mounts fresh per conversation via toggle+Show. */
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

  createEffect(() => {
    const msgs = chat.messages();
    if (msgs.length > 0) {
      store.saveCurrentMessages(msgs);
      const title = deriveTitle(msgs);
      if (title) store.updateCurrentTitle(title);
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

  // Toggle this off/on to force ConversationChat unmount/remount
  const [visible, setVisible] = createSignal(false);
  let initDone = false;

  // On initial corpus mount: load most recent conversation
  createEffect(
    on(
      () => corpus(),
      (c) => {
        if (!c) return;
        const convs = store.conversations().filter((conv) => conv.corpusId === c.id);
        if (convs.length > 0) store.switchTo(convs[0].id);
        else store.createNew(c.id);
        setVisible(true);
      },
    ),
  );

  // When sidebar selects a different conversation: unmount + remount
  createEffect(() => {
    const id = store.currentId();
    if (!id) return;
    if (!initDone) { initDone = true; return; }
    setVisible(false);
    setTimeout(() => setVisible(true), 0);
  });

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
      <Show when={visible() && corpus() && !isLoading() && store.currentId()}>
        <ConversationChat convId={store.currentId()} corpusSlug={params.slug} />
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
