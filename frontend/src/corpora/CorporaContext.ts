import { createSignal, createResource } from "solid-js";

/** Shape returned by GET /api/corpora. */
export interface Corpus {
  id: string;
  slug: string;
  name: string;
  description: string;
  chunker: string;
}

export interface CorporaState {
  corpora: () => Corpus[];
  loading: () => boolean;
  error: () => string | null;
  resolveSlug: (slug: string) => Corpus | undefined;
  resolveId: (id: string) => Corpus | undefined;
  retry: () => void;
}

type FetchResult = { data: Corpus[] } | { error: string };

export function createCorporaContext(opts?: {
  fetch?: typeof globalThis.fetch;
}): CorporaState {
  const fetcher = opts?.fetch ?? globalThis.fetch;
  const [error, setError] = createSignal<string | null>(null);

  const [corporaResource, { refetch }] = createResource(
    async (): Promise<Corpus[]> => {
      const res = await fetcher("/api/corpora");
      if (!res.ok) {
        const msg = "Failed to load knowledge bases";
        setError(msg);
        return [];
      }
      setError(null);
      return res.json() as Promise<Corpus[]>;
    },
  );

  return {
    corpora: () => corporaResource() ?? [],
    loading: () => corporaResource.loading,
    error,
    resolveSlug: (slug: string) =>
      (corporaResource() ?? []).find((c) => c.slug === slug),
    resolveId: (id: string) =>
      (corporaResource() ?? []).find((c) => c.id === id),
    retry: () => {
      setError(null);
      refetch();
    },
  };
}
