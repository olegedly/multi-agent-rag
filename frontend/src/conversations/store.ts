/// <reference types="vite/client" />

import { createSignal, createMemo } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  messages: UIMessage[];
  /** Persisted mapping of messageId → agent name, survives page reload. */
  agentNames?: Record<string, string>;
}


export interface ConversationPersistence {
  /** Load all persisted conversations. */
  loadAll(): Conversation[];
  /** Persist a conversation. Throws QuotaExceededError on storage full. */
  save(conv: Conversation): void;
  /** Remove a conversation by id. */
  remove(id: string): void;
  /** Load the last opened conversation id, if any. */
  loadLastOpened(): string | undefined;
  /** Persist the last opened conversation id. */
  saveLastOpened(id: string): void;
}


export const localStoragePersistence: ConversationPersistence = {
  loadAll(): Conversation[] {
    const convs: Conversation[] = [];
    const errors: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(LS_PREFIX) && key !== LS_LAST_OPENED) {
        try {
          const parsed = JSON.parse(localStorage.getItem(key)!);
          if (parsed && typeof parsed.id === "string") {
            convs.push(parsed);
          }
        } catch {
          errors.push(key);
        }
      }
    }
    if (errors.length > 0) {
      console.warn("Skipped corrupt conversation keys:", errors.join(", "));
    }
    return convs;
  },

  save(conv: Conversation) {
    try {
      localStorage.setItem(lsKey(conv.id), JSON.stringify(conv));
    } catch (e) {
      if (e instanceof DOMException && e.name === "QuotaExceededError") {
        throw e;
      }
    }
  },

  remove(id: string) {
    localStorage.removeItem(lsKey(id));
  },

  loadLastOpened(): string | undefined {
    return localStorage.getItem(LS_LAST_OPENED) ?? undefined;
  },

  saveLastOpened(id: string) {
    localStorage.setItem(LS_LAST_OPENED, id);
  },
};

const LS_PREFIX = "conversation:";
const LS_LAST_OPENED = "conversation:lastOpened";

function lsKey(id: string) {
  return `${LS_PREFIX}${id}`;
}


function createConversation(): Conversation {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    createdAt: Date.now(),
    messages: [],
    agentNames: {},
  };
}

export interface ConversationStore {
  conversations: () => Conversation[];
  currentId: () => string;
  currentConversation: () => Conversation | undefined;
  getCurrentMessages: () => UIMessage[];
  getCurrentAgentNames: () => Record<string, string>;
  createNew: () => string;
  switchTo: (id: string) => void;
  saveCurrentMessages: (messages: UIMessage[], agentNames?: Record<string, string>) => void;
  removeCurrent: () => void;
  updateCurrentTitle: (title: string) => void;
  storageError: () => string | null;
  setStorageError: (err: string | null) => void;
}

export function createConversationStore(opts?: {
  persistence?: ConversationPersistence;
}): ConversationStore {
  const p = opts?.persistence ?? localStoragePersistence;
  let loaded = p.loadAll();
  let lastOpened = p.loadLastOpened();

  if (loaded.length === 0) {
    const first = createConversation();
    loaded = [first];
    p.save(first);
    p.saveLastOpened(first.id);
    lastOpened = first.id;
  }

  // Restore last opened conversation; if not found, use first
  const initialId =
    lastOpened && loaded.some((c) => c.id === lastOpened)
      ? lastOpened
      : loaded[0].id;

  const [conversations, setConversations] = createSignal<Conversation[]>(loaded);
  const [currentId, setCurrentId] = createSignal<string>(initialId);
  const [storageError, setStorageError] = createSignal<string | null>(null);

  const currentConversation = createMemo(() =>
    conversations().find((c) => c.id === currentId())
  );


  function getConversationList(): Conversation[] {
    // Return sorted newest first
    return [...conversations()].sort((a, b) => b.createdAt - a.createdAt);
  }

  return {
    conversations: getConversationList,
    currentId,
    currentConversation,

    getCurrentMessages() {
      const cur = currentConversation();
      return cur ? [...cur.messages] : [];
    },

    getCurrentAgentNames(): Record<string, string> {
      const cur = currentConversation();
      return cur?.agentNames ?? {};
    },

    createNew() {
      // If there's already a fresh empty conversation (title "New conversation",
      // no messages), switch to it instead of creating a duplicate. This
      // prevents the "+ New" button from piling up empty conversations.
      const existing = conversations().find(
        (c) => c.title === "New conversation" && c.messages.length === 0,
      );
      if (existing) {
        setCurrentId(existing.id);
        p.saveLastOpened(existing.id);
        return existing.id;
      }

      const conv = createConversation();
      const convs = [...conversations(), conv];
      p.save(conv);
      setCurrentId(conv.id);
      p.saveLastOpened(conv.id);
      setConversations(convs);
      return conv.id;
    },

    switchTo(id: string) {
      if (conversations().some((c) => c.id === id)) {
        setCurrentId(id);
        p.saveLastOpened(id);
      }
    },

    saveCurrentMessages(messages: UIMessage[], agentNames?: Record<string, string>) {
      const cur = currentConversation();
      if (!cur) return;

      // Defense in depth: never overwrite non-empty localStorage data
      // with an empty message array. This prevents any caller error
      // (e.g., a stale beforeunload handler or HMR teardown race)
      // from silently wiping a conversation's history.
      if (messages.length === 0 && cur.messages.length > 0) return;
      const updated: Conversation = {
        ...cur,
        messages,
        agentNames: agentNames ?? cur.agentNames,
      };
      // Mutate the conversations array
      const convs = conversations().map((c) =>
        c.id === cur.id ? updated : c
      );
      try {
        p.save(updated);
        setStorageError(null);
      } catch (e) {
        if (e instanceof DOMException && e.name === "QuotaExceededError") {
          setStorageError("Storage quota exceeded. Please delete some conversations.");
          return;
        }
      }
      setConversations(convs);
    },

    removeCurrent() {
      const id = currentId();
      const convs = conversations().filter((c) => c.id !== id);
      p.remove(id);

      if (convs.length === 0) {
        // Last one — auto-create a fresh conversation
        const fresh = createConversation();
        const newConvs = [fresh];
        p.save(fresh);
        p.saveLastOpened(fresh.id);
        setConversations(newConvs);
        setCurrentId(fresh.id);
      } else {
        // Sort by createdAt descending; pick the newest (or first if not found)
        const sorted = [...convs].sort((a, b) => b.createdAt - a.createdAt);
        const nextId = sorted[0].id;
        p.saveLastOpened(nextId);
        setConversations(sorted);
        setCurrentId(nextId);
      }
    },

    updateCurrentTitle(title: string) {
      const cur = currentConversation();
      if (!cur) return;
      const updated: Conversation = { ...cur, title };
      const convs = conversations().map((c) =>
        c.id === cur.id ? updated : c
      );
      p.save(updated);
      setConversations(convs);
    },

    storageError,
    setStorageError,
  };
}
