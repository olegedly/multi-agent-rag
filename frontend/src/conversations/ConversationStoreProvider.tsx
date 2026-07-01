import { createContext, useContext, type JSX } from "solid-js";
import { createConversationStore, type ConversationStore } from "./store";

const ConversationStoreContext = createContext<ConversationStore>();

export function ConversationStoreProvider(props: {
  children: JSX.Element;
  defaultCorpusId?: string;
}) {
  const store = createConversationStore({ defaultCorpusId: props.defaultCorpusId });
  return (
    <ConversationStoreContext.Provider value={store}>
      {props.children}
    </ConversationStoreContext.Provider>
  );
}

export function useConversationStore(): ConversationStore {
  const ctx = useContext(ConversationStoreContext);
  if (!ctx) throw new Error("useConversationStore must be used within a ConversationStoreProvider");
  return ctx;
}
