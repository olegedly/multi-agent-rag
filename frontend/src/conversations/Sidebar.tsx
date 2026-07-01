import { For, Show, createSignal, createMemo } from "solid-js";
import type { Conversation } from "./store";

interface SidebarProps {
  conversations: Conversation[];
  currentId: string;
  activeCorpusId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar(props: SidebarProps) {
  const [confirmingId, setConfirmingId] = createSignal<string | null>(null);

  // Filter conversations to only those belonging to the active corpus
  const filtered = createMemo(() =>
    props.conversations.filter((c) => c.corpusId === props.activeCorpusId),
  );

  const enriched = createMemo(() => {
    const currId = props.currentId;
    const confirmId = confirmingId();
    return filtered().map((conv) => ({
      conv,
      isCurrent: conv.id === currId,
      isConfirming: confirmId === conv.id,
    }));
  });

  const handleDelete = (id: string) => {
    if (confirmingId() === id) {
      props.onDelete(id);
      setConfirmingId(null);
    } else {
      setConfirmingId(id);
    }
  };

  return (
    <>
      <Show when={props.isOpen}>
        {/* Mobile backdrop */}
        <div
          class="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={props.onClose}
        />
      </Show>
      <aside
      class={`fixed md:static inset-y-0 left-0 z-30 w-72 bg-(--sidebar-bg) border-r border-(--border) flex flex-col transition-transform ${
        props.isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      }`}
    >
      {/* Header */}
      <div class="flex items-center justify-between p-4 border-b border-(--border)">
        <h2 class="text-sm font-semibold text-(--text-primary) uppercase tracking-wide">
          Conversations
        </h2>
        <button
          onClick={props.onNew}
          class="px-3 py-1 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors cursor-pointer"
        >
          + New
        </button>
      </div>

      {/* List */}
      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <Show
          when={enriched().length > 0}
          fallback={
            <p class="text-sm text-(--text-secondary) text-center py-8">
              No conversations
            </p>
          }
        >
          <For each={enriched()}>
            {(item) => {
              const { conv, isCurrent, isConfirming } = item;
              return (
                <div
                  class={`group flex items-center justify-between px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors ${
                    isCurrent
                      ? "bg-(--accent) text-white"
                      : "text-(--text-primary) hover:bg-(--hover)"
                  }`}
                  onClick={() => {
                    if (!isConfirming) {
                      props.onSelect(conv.id);
                      props.onClose();
                    }
                  }}
                >
                  <span class="truncate flex-1">{conv.title}</span>

                  <Show
                    when={isConfirming}
                    fallback={
                      <button
                        class="opacity-0 group-hover:opacity-100 p-1 text-(--text-secondary) hover:text-(--danger) transition-all cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(conv.id);
                        }}
                        title="Delete conversation"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          class="h-4 w-4"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fill-rule="evenodd"
                            d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                            clip-rule="evenodd"
                          />
                        </svg>
                      </button>
                    }
                  >
                    <div class="flex gap-1">
                      <button
                        class="p-1 text-green-500 hover:text-green-400 transition-colors cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(conv.id);
                        }}
                        title="Confirm delete"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          class="h-4 w-4"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fill-rule="evenodd"
                            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                            clip-rule="evenodd"
                          />
                        </svg>
                      </button>
                      <button
                        class="p-1 text-(--text-secondary) hover:text-(--text-primary) transition-colors cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmingId(null);
                        }}
                        title="Cancel delete"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          class="h-4 w-4"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fill-rule="evenodd"
                            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                            clip-rule="evenodd"
                          />
                        </svg>
                      </button>
                    </div>
                  </Show>
                </div>
              );
            }}
          </For>
        </Show>
      </div>
    </aside>
    </>
  );
}
