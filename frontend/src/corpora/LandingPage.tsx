import { Show, For, type Component } from "solid-js";
import { A } from "@solidjs/router";
import { useCorpora } from "./CorporaProvider";

export const LandingPage: Component = () => {
  const corpora = useCorpora();

  return (
    <div class="flex flex-col items-center justify-center h-full px-6 py-12">
      <div class="max-w-2xl w-full">
        <p class="text-(--text-secondary) text-center mb-8 text-lg">
          Multi-agent research assistant grounded in curated knowledge bases.
          Ask questions and get cited, synthesized answers from multiple AI agents.
        </p>

        <Show when={corpora.loading()}>
          <div class="flex justify-center py-12">
            <p class="text-(--text-secondary)">Loading knowledge bases...</p>
          </div>
        </Show>

        <Show when={corpora.error()}>
          <div class="flex flex-col items-center gap-4 py-12">
            <p class="text-red-500">{corpora.error()}</p>
            <button
              onClick={() => corpora.retry()}
              class="px-4 py-2 text-sm bg-(--accent) text-white rounded hover:bg-(--accent-hover) transition-colors cursor-pointer"
            >
              Retry
            </button>
          </div>
        </Show>

        <Show when={!corpora.loading() && !corpora.error()}>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <For each={corpora.corpora()}>
              {(corpus) => (
                <A
                  href={`/corpora/${corpus.slug}`}
                  class="block p-5 rounded-lg border border-(--border) bg-(--hover) hover:border-(--accent) hover:shadow-md transition-all no-underline"
                >
                  <h3 class="text-base font-semibold text-(--text-primary) mb-1">
                    {corpus.name}
                  </h3>
                  <p class="text-sm text-(--text-secondary) leading-normal">
                    {corpus.description}
                  </p>
                </A>
              )}
            </For>
          </div>

          <Show when={corpora.corpora().length === 0}>
            <p class="text-(--text-secondary) text-center py-12">
              No knowledge bases available.
            </p>
          </Show>
        </Show>
      </div>
    </div>
  );
};
