/// <reference types="vite/client" />

import { createSignal, createMemo } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";

export interface Conversation {
  id: string;
  corpusId: string;
  title: string;
  createdAt: number;
  /** Timestamp of the most recent message or creation time if no messages yet. */
  updatedAt: number;
  messages: UIMessage[];
  /** Mode: single-agent (default) or multi-agent pipeline. */
  mode: "single" | "multi";
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

function createConversation(corpusId: string): Conversation {
  const now = Date.now();
  return {
    id: crypto.randomUUID(),
    corpusId,
    title: "New conversation",
    createdAt: now,
    updatedAt: now,
    messages: [],
    mode: "single",
    agentNames: {},
  };
}

export interface ConversationStore {
  conversations: () => Conversation[];
  currentId: () => string;
  currentConversation: () => Conversation | undefined;
  getCurrentMessages: () => UIMessage[];
  getCurrentAgentNames: () => Record<string, string>;
  createNew: (corpusId?: string) => string;
  switchTo: (id: string) => void;
  saveCurrentMessages: (messages: UIMessage[], agentNames?: Record<string, string>) => void;
  removeCurrent: () => void;
  updateCurrentTitle: (title: string) => void;
  updateCurrentMode: (mode: "single" | "multi") => void;
  storageError: () => string | null;
  setStorageError: (err: string | null) => void;
}

export function createConversationStore(opts?: {
  persistence?: ConversationPersistence;
  defaultCorpusId?: string;
}): ConversationStore {
  const p = opts?.persistence ?? localStoragePersistence;
  const defaultCorpusId = opts?.defaultCorpusId ?? "";
  let loaded = p.loadAll();
  let lastOpened = p.loadLastOpened();

  // Record whether we've migrated anything so we can persist once at the end
  let migrated = false;
  loaded = loaded.map((c) => {
    let changed = false;

    // Legacy: assign defaultCorpusId to conversations without one
    if (!c.corpusId) {
      c = { ...c, corpusId: defaultCorpusId };
      changed = true;
    }

    // Legacy: fix conversations whose updatedAt doesn't match their newest message.
    // The old conversation-switching bug was re-saving every conversation on
    // every mount with Date.now(), corrupting all updatedAt timestamps.
    let fixedUpdatedAt: number | undefined;
    if (c.messages.length > 0) {
      // Derive from the last message's createdAt (or updatedAt from the last assistant message)
      const lastMsg = c.messages[c.messages.length - 1];
      const msgTime = lastMsg.createdAt instanceof Date
        ? lastMsg.createdAt.getTime()
        : typeof lastMsg.createdAt === 'number'
          ? lastMsg.createdAt
          : typeof lastMsg.createdAt === 'string'
            ? new Date(lastMsg.createdAt).getTime()
            : undefined;
      if (msgTime !== undefined && Math.abs(msgTime - c.updatedAt) > 5000) {
        fixedUpdatedAt = msgTime;
      }
    } else {
      // Empty conversation — updatedAt should equal createdAt
      if (c.updatedAt !== c.createdAt && c.createdAt > 0) {
        fixedUpdatedAt = c.createdAt;
      }
    }

    if (fixedUpdatedAt !== undefined) {
      c = { ...c, updatedAt: fixedUpdatedAt };
      changed = true;
    }

    // Legacy: infer mode from agentNames
    if (!c.mode) {
      const names = Object.values(c.agentNames ?? {});
      const hasMultiAgent = names.some((n) =>
        ["Researcher", "Critic", "Synthesizer"].includes(n)
      );
      c = { ...c, mode: hasMultiAgent ? "multi" : "single" };
      changed = true;
    }

    if (changed) migrated = true;
    return c;
  });
  // Persist any migrations
  if (migrated) {
    loaded.forEach((c) => p.save(c));
  }

  if (loaded.length === 0) {
    const first = createConversation(defaultCorpusId);
    loaded = [first];
    p.save(first);
    p.saveLastOpened(first.id);
    lastOpened = first.id;
  }

  // Restore last opened conversation; if not found, use most recently updated
  const initialId =
    lastOpened && loaded.some((c) => c.id === lastOpened)
      ? lastOpened
      : sortedByUpdatedAt(loaded)[0].id;

  const [conversations, setConversations] = createSignal<Conversation[]>(loaded);
  const [currentId, setCurrentId] = createSignal<string>(initialId);
  const [storageError, setStorageError] = createSignal<string | null>(null);

  const currentConversation = createMemo(() =>
    conversations().find((c) => c.id === currentId())
  );

  function sortedByUpdatedAt(convs: Conversation[]): Conversation[] {
    return [...convs].sort((a, b) => b.updatedAt - a.updatedAt);
  }

  function getConversationList(): Conversation[] {
    return sortedByUpdatedAt(conversations());
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

    createNew(corpusId?: string) {
      const targetCorpusId = corpusId ?? defaultCorpusId;

      // De-duplication: only match empty conversations in the same corpus
      const existing = conversations().find(
        (c) =>
          c.corpusId === targetCorpusId &&
          c.title === "New conversation" &&
          c.messages.length === 0,
      );
      if (existing) {
        setCurrentId(existing.id);
        p.saveLastOpened(existing.id);
        // Bump updatedAt so the reused entry sorts to the top
        const bumped: Conversation = { ...existing, updatedAt: Date.now() };
        p.save(bumped);
        setConversations(
          sortedByUpdatedAt(
            conversations().map((c) => (c.id === existing.id ? bumped : c)),
          ),
        );
        return existing.id;
      }

      const conv = createConversation(targetCorpusId);
      // Prepend so the new conversation sorts first even when timestamps tie
      // (stable sort preserves relative order for equal keys)
      const convs = sortedByUpdatedAt([conv, ...conversations()]);
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
      // with an empty message array.
      if (messages.length === 0 && cur.messages.length > 0) return;
      const updated: Conversation = {
        ...cur,
        messages,
        updatedAt: Date.now(),
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
        const fresh = createConversation(defaultCorpusId);
        const newConvs = [fresh];
        p.save(fresh);
        p.saveLastOpened(fresh.id);
        setConversations(newConvs);
        setCurrentId(fresh.id);
      } else {
        // Sort by updatedAt descending; pick the most recently updated
        const sorted = sortedByUpdatedAt(convs);
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

    updateCurrentMode(mode: "single" | "multi") {
      const cur = currentConversation();
      if (!cur) return;
      const updated: Conversation = { ...cur, mode };
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
