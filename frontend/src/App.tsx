import { For, Show, createSignal } from "solid-js";
import { fetchServerSentEvents, useChat } from "@tanstack/ai-solid";

const App = () => {
  const [input, setInput] = createSignal("");

  const { messages, sendMessage, isLoading, error } = useChat({
    connection: fetchServerSentEvents("/api/chat"),
  });

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    const text = input().trim();
    if (text && !isLoading()) {
      sendMessage(text);
      setInput("");
    }
  };

  return (
    <main class="flex flex-col items-center justify-center min-h-dvh gap-4 bg-gray-800 text-white">
      <h2 class="text-4xl mb-4">Chat with LLM</h2>

      <Show when={error()}>
        <div class="w-full max-w-3xl bg-red-900/50 border border-red-500 text-red-200 px-4 py-3 rounded">
          {error()?.message}
        </div>
      </Show>

      <div class="border-slate-400 bg-gray-700 min-h-120 w-3xl border px-3 py-2 overflow-y-auto">
        <For each={messages()}>
          {(msg) => (
            <div>
              <strong>{msg.role}: </strong>
              <For each={msg.parts}>
                {(part) => (
                  <>{part.type === "text" && <span>{part.content}</span>}</>
                )}
              </For>
            </div>
          )}
        </For>
      </div>
      <form onSubmit={handleSubmit} class="flex w-3xl gap-2">
        <textarea
          value={input()}
          onInput={(e) => setInput(e.currentTarget.value)}
          disabled={isLoading()}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          class="border-2 transition-colors border-amber-100 focus:border-blue-400 outline-0 block resize-none min-h-25 p-2 flex-1 bg-amber-100 text-black"
        />
        <button
          type="submit"
          disabled={isLoading()}
          class="ml-auto px-6 bg-amber-300 hover:bg-amber-400 transition-colors text-slate-800 cursor-pointer disabled:opacity-50"
        >
          {isLoading() ? "..." : "Send"}
        </button>
      </form>
    </main>
  );
};

export default App;
