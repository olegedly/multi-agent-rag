import type { Component } from "solid-js";

const App: Component = () => {
  return (
    <main class="flex flex-col items-center justify-center min-h-dvh gap-4 bg-gray-800 text-white">
      <h2 class="text-4xl mb-4">Chat with LLM</h2>
      <div class="border-slate-400 bg-gray-700 min-h-120 min-w-3xl border px-3 py-2"></div>
      <div class="flex min-w-3xl gap-2">
        <textarea class="border-2 transition-colors border-amber-100 focus:border-blue-400 outline-0 block resize-none min-h-25 p-2 flex-1 bg-amber-100 text-black" />
        <button
          type="button"
          class="ml-auto px-6 bg-amber-300 hover:bg-amber-400 transition-colors text-slate-800 cursor-pointer"
        >
          Send
        </button>
      </div>
    </main>
  );
};

export default App;
