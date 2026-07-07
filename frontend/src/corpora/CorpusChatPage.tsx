import { Show, For, createEffect, on, untrack, createSignal, type Component } from "solid-js";
import { A, useParams } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";
import { useConversationStore } from "@/conversations/ConversationStoreProvider";
import { ChatView } from "@/chat/ChatView";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import type { StreamChunk } from "@tanstack/ai/client";
import { resilientFetch } from "@/chat/resilientFetch";
import { generateTitle } from "@/conversations/title";


/** Chat session — mounted per conversation via For's keyed lifecycle. */
const ConversationChat: Component<{ convId: string; corpusSlug: string }> = (props) => {
  const store = useConversationStore();
  const sseUrl = () => `/api/chat/${props.corpusSlug}`;

  // Agent name tracking — captured from TEXT_MESSAGE_START stream chunks
  const [agentNameMap, setAgentNameMap] = createSignal<Record<string, string>>(
    store.getCurrentAgentNames(),
  );
  // Set of message IDs that have received TEXT_MESSAGE_END
  const [endedMessageIds, setEndedMessageIds] = createSignal<Set<string>>(new Set());

  // ── Mode state (decoupled from conversations() reactivity) ──────────
  // Use a local signal so rendering doesn't depend on store.conversations().
  // Reading store.conversations() in the JSX return creates a reactive
  // dependency that causes full re-renders during streaming (every chunk
  // calls saveCurrentMessages → setConversations), which destroys
  // <For>/<Index> child components and resets collapse/expand state.
  const convMode: "single" | "multi" =
    (store.conversations().find((c) => c.id === props.convId)?.mode ?? "single") as "single" | "multi";
  const [localMode, setLocalMode] = createSignal<"single" | "multi">(convMode);
  // Toggle is hidden once the first message has been sent.
  const [toggleLocked, setToggleLocked] = createSignal(
    store.getCurrentMessages().length > 0
  );

  const chat = useChat({
    id: `chat-${props.convId}`,
    initialMessages: store.getCurrentMessages(),
    get connection() {
      return fetchServerSentEvents(sseUrl(), {
        fetchClient: resilientFetch,
      });
    },
    // Getter so TanStack's sync effect tracks the local signal
    // (which only changes on user toggle, NOT on streaming saves).
    get forwardedProps() {
      return { mode: localMode() };
    },
    onChunk: (chunk: StreamChunk) => {
      if (
        chunk.type === "TEXT_MESSAGE_START" &&
        "name" in chunk &&
        typeof (chunk as any).name === "string"
      ) {
        const name = (chunk as any).name as string;
        setAgentNameMap((prev) => ({ ...prev, [chunk.messageId]: name }));
      }
      if (chunk.type === "TEXT_MESSAGE_END") {
        setEndedMessageIds((prev) => new Set(prev).add(chunk.messageId));
      }
    },
  });

  // Persist messages + agent names when they change AFTER initial mount
  let initial = true;
  createEffect(() => {
    const msgs = chat.messages();
    if (initial) { initial = false; return; }
    if (msgs.length > 0) {
      untrack(() => store.saveCurrentMessages(msgs, agentNameMap()));
    }
  });

  // Derive title when new user messages arrive — skip initial load so
  // existing titles (including custom ones) aren't overwritten on remount.
  let prevMsgCount = 0;
  createEffect(() => {
    const msgs = chat.messages();
    if (msgs.length > prevMsgCount) {
      prevMsgCount = msgs.length;
      const title = deriveTitle(msgs);
      if (title) {
        untrack(() => store.updateCurrentTitle(title));
      }
    } else {
      prevMsgCount = msgs.length;
    }
  });

  const handleSend = (text: string) => {
    const msgs = chat.messages();
    if (msgs.length === 0) store.updateCurrentTitle(generateTitle(text));
    chat.sendMessage(text);
    // Lock toggle after first message — mode was already captured
    // by forwardedProps at POST time.
    setToggleLocked(true);
  };

  // Persist mode change to the conversation store AND local signal
  const handleModeChange = (newMode: "single" | "multi") => {
    store.updateCurrentMode(newMode);
    setLocalMode(newMode);
  };

  return (
    <ChatView
      messages={chat.messages}
      isLoading={chat.isLoading()}
      error={chat.error()?.message ?? null}
      storageError={store.storageError()}
      agentNameMap={agentNameMap()}
      onSend={handleSend}
      endedMessageIds={endedMessageIds()}
      onStop={() => chat.stop()}
      onDismissStorageError={() => store.setStorageError(null)}
      focusTick={0}
      mode={toggleLocked() ? undefined : localMode()}
      onModeChange={handleModeChange}
    />
  );
};

export const CorpusChatPage: Component = () => {
  const params = useParams();
  const corpora = useCorpora();
  const store = useConversationStore();

  const corpus = () => (params.slug ? corpora.resolveSlug(params.slug) : undefined);
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
            <ConversationChat convId={convId} corpusSlug={params.slug!} />
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
