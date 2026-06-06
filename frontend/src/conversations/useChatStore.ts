import { onCleanup, onMount } from "solid-js";
import { fetchServerSentEvents, useChat } from "@tanstack/ai-solid";
import type { UIMessage } from "@tanstack/ai-client";
import {
  createConversationStore,
  type ConversationStore,
} from "./store";

const SAVE_KEY = "chat:hasUnsaved";

export function useChatStore() {
  const store = createConversationStore();

  const chat = useChat({
    connection: fetchServerSentEvents("/api/chat"),
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
    // Clear current chat
    chat.setMessages([]);
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
    // Clear messages first so we don't save stale refs
    chat.setMessages([]);
    store.removeCurrent();
    const msgs = store.getCurrentMessages();
    chat.setMessages(msgs);
  };

  // Send message with auto-title
  const sendMessage = (text: string) => {
    // Derive title from the message being sent
    const msgs = chat.messages();
    if (msgs.length === 0) {
      // First message — set title before sending
      const title = deriveTitleFromText(text);
      store.updateCurrentTitle(title);
    }
    chat.sendMessage(text);
  };

  // beforeunload safety net
  onMount(() => {
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
    stop: chat.stop,
    clear: chat.clear,
    switchTo,
    createNew,
    deleteCurrent,
  };
}

function deriveTitleFromText(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length === 0) return "New conversation";
  if (trimmed.length <= 50) return trimmed;
  const truncated = trimmed.slice(0, 50);
  const lastSpace = truncated.lastIndexOf(" ");
  const result = lastSpace > 0 ? truncated.slice(0, lastSpace) : truncated;
  return result.replace(/[\s\p{P}]+$/u, "");
}

function deriveTitle(msgs: UIMessage[]): string | null {
  const firstUser = msgs.find((m) => m.role === "user");
  if (!firstUser) return null;
  const text = firstUser.parts
    .filter((p) => p.type === "text")
    .map((p) => p.content)
    .join(" ");
  return deriveTitleFromText(text);
}
