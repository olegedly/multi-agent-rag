import { onCleanup, onMount } from "solid-js";
import { fetchServerSentEvents, useChat } from "@tanstack/ai-solid";
import type { UIMessage } from "@tanstack/ai-client";
import { createConversationStore } from "./store";
import { generateTitle } from "./title";
import { resilientFetch } from "./resilientFetch";

const SAVE_KEY = "chat:hasUnsaved";

export function useChatStore() {
  const store = createConversationStore();

  const chat = useChat({
    connection: fetchServerSentEvents("/api/chat/eu-ai-act", {
      fetchClient: resilientFetch,
    }),
  });

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
    // Clear messages and error state before loading saved messages.
    // We use chat.clear() (not chat.setMessages([])) because clear()
    // also calls setError(undefined), clearing any stale error from
    // the previous conversation.
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
    // Clear current chat (messages + error state)
    chat.clear();
    store.createNew();
    localStorage.removeItem(SAVE_KEY);
  };

  // Delete current conversation and switch
  const deleteCurrent = () => {
    const id = store.currentId();
    const wasLoading = chat.isLoading();
    if (wasLoading) {
      chat.stop();
    }
    // Don't save — user explicitly deleted
    // Clear messages and error state first
    chat.clear();
    store.removeCurrent();
    const msgs = store.getCurrentMessages();
    chat.setMessages(msgs);
  };

  /**
   * Optimistically stop the stream AND finalize any in-flight message
   * parts so the UI doesn't show stale "streaming" states.
   *
   * ChatClient.stop() aborts the HTTP request and sets isLoading=false,
   * but the processor's assistant message may still have tool-call parts
   * stuck in "input-streaming" / "streaming" state because finalizeStream()
   * runs asynchronously after the UI has already re-rendered. We fix this
   * by cloning the messages and marking incomplete parts as complete.
   */
  const stop = () => {
    chat.stop();
    // After stop(), finalize any in-progress parts in the current
    // assistant message. This is an optimistic UI update — it runs
    // synchronously after the abort, before the library's internal
    // finalizeStream() catches up.
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
      // Use setTimeout to avoid mutating state during the current
      // reactive tick — the library may still be propagating its
      // own state changes.
      setTimeout(() => chat.setMessages(updated), 0);
    }
  };

  // Send message with auto-title
  const sendMessage = (text: string) => {
    // Derive title from the message being sent
    const msgs = chat.messages();
    if (msgs.length === 0) {
      // First message — set title before sending
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

    // beforeunload safety net
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
    // Store state
    conversations: store.conversations,
    currentId: store.currentId,
    storageError: store.storageError,
    dismissStorageError: () => store.setStorageError(null),

    // Chat state (from useChat)
    messages: chat.messages,
    isLoading: () => chat.isLoading(),
    error: () => chat.error()?.message ?? null,
    status: chat.status,
    connectionStatus: chat.connectionStatus,

    // Actions
    sendMessage,
    stop,
    clear: chat.clear,
    switchTo,
    createNew,
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
