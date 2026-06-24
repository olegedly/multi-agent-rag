import { onCleanup, onMount, createSignal } from "solid-js";
import { fetchServerSentEvents, useChat } from "@tanstack/ai-solid";
import type { UIMessage } from "@tanstack/ai-client";
import type { StreamChunk } from "@tanstack/ai";
import { createConversationStore } from "./store";
import { generateTitle } from "./title";
import { resilientFetch } from "./resilientFetch";

const SAVE_KEY = "chat:hasUnsaved";

export function useChatStore() {
  const store = createConversationStore();

  // Map of messageId → agent name (captured from TEXT_MESSAGE_START events)
  const [agentNameMap, setAgentNameMap] = createSignal<Record<string, string>>({});
  // Set of message IDs that have received TEXT_MESSAGE_END.
  // Used to collapse thinking blocks when their agent finishes.
  const [endedMessageIds, setEndedMessageIds] = createSignal<Set<string>>(new Set());

  const chat = useChat({
    connection: fetchServerSentEvents("/api/chat/eu-ai-act", {
      fetchClient: resilientFetch,
    }),
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

  // Tick that increments when a new conversation is created, so
  // ChatInput can re-focus after the creation.
  const [focusTick, setFocusTick] = createSignal(0);

  // Save current messages when switching conversations
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

  // Save on conversation switch
  const switchTo = (id: string) => {
    if (id === store.currentId()) return;
    const wasLoading = chat.isLoading();
    if (wasLoading) {
      chat.stop();
    }
    saveCurrent();
    chat.clear();
    store.switchTo(id);
    const msgs = store.getCurrentMessages();
    chat.setMessages(msgs);
  };

  // Create new conversation
  const createNew = () => {
    saveCurrent();
    const wasLoading = chat.isLoading();
    if (wasLoading) {
      chat.stop();
    }
    chat.clear();
    store.createNew();
    localStorage.removeItem(SAVE_KEY);
    setFocusTick((t) => t + 1);
  };

  // Delete current conversation and switch
  const deleteCurrent = () => {
    const id = store.currentId();
    const wasLoading = chat.isLoading();
    if (wasLoading) {
      chat.stop();
    }
    chat.clear();
    store.removeCurrent();
    const msgs = store.getCurrentMessages();
    chat.setMessages(msgs);
  };

  const stop = () => {
    chat.stop();
    const msgs = chat.messages();
    const updated = msgs.map((msg) => {
      if (msg.role !== "assistant") return msg;
      let changed = false;
      const newParts = msg.parts.map((part) => {
        if (part.type === "tool-call") {
          if (part.state !== "complete") {
            changed = true;
            return { ...part, state: "complete" as const };
          }
        }
        if (part.type === "tool-result") {
          if (part.state !== "complete") {
            changed = true;
            return { ...part, state: "complete" as const };
          }
        }
        return part;
      });
      if (!changed) return msg;
      return { ...msg, parts: newParts };
    });
    if (updated !== msgs) {
      setTimeout(() => chat.setMessages(updated), 0);
    }
  };

  // Send message with auto-title
  const sendMessage = (text: string) => {
    const msgs = chat.messages();
    if (msgs.length === 0) {
      store.updateCurrentTitle(generateTitle(text));
    }
    chat.sendMessage(text);
  };

  // Load current conversation's messages into chat on initial mount
  onMount(() => {
    const initialMsgs = store.getCurrentMessages();
    if (initialMsgs.length > 0) {
      chat.setMessages(initialMsgs);
    }

    const handleBeforeUnload = () => {
      const msgs = chat.messages();
      if (msgs.length > 0) {
        localStorage.setItem(SAVE_KEY, "true");
        saveCurrent();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    onCleanup(() => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    });
  });

  return {
    conversations: store.conversations,
    currentId: store.currentId,
    storageError: store.storageError,
    dismissStorageError: () => store.setStorageError(null),
    messages: chat.messages,
    isLoading: () => chat.isLoading(),
    error: () => chat.error()?.message ?? null,
    status: chat.status,
    connectionStatus: chat.connectionStatus,
    agentNameMap,
    endedMessageIds,
    sendMessage,
    stop,
    clear: chat.clear,
    switchTo,
    createNew,
    focusTick,
    deleteCurrent,
  };
}

function deriveTitle(msgs: UIMessage[]): string | null {
  const firstUser = msgs.find((m) => m.role === "user");
  if (!firstUser) return null;
  const text = firstUser.parts
    .filter((p) => p.type === "text")
    .map((p) => p.content)
    .join(" ");
  if (text.length === 0) return null;
  return generateTitle(text);
}
