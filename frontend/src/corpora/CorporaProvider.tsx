import { createContext, useContext, createSignal, type Accessor, type JSX } from "solid-js";
import { createCorporaContext, type Corpus, type CorporaState } from "./CorporaContext";

const CorporaContext = createContext<CorporaState>();

export function CorporaProvider(props: {
  children: JSX.Element;
  fetch?: typeof globalThis.fetch;
}) {
  const state = createCorporaContext({ fetch: props.fetch });
  return (
    <CorporaContext.Provider value={state}>
      {props.children}
    </CorporaContext.Provider>
  );
}

export function useCorpora(): CorporaState {
  const ctx = useContext(CorporaContext);
  if (!ctx) throw new Error("useCorpora must be used within a CorporaProvider");
  return ctx;
}
