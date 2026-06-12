import {
  createSignal,
  createEffect,
  onMount,
  onCleanup,
  on,
  useContext,
  type JSX,
} from "solid-js";
import { StopCollapseContext } from "./ChatView";

export interface CollapsibleSectionProps {
  label: string;
  /** Optional leading icon rendered before the label */
  leadingIcon?: JSX.Element;
  children: JSX.Element;
  expanded?: boolean;
  onToggle?: (expanded: boolean) => void;
  /** Auto-collapse after this many ms when user hasn't interacted */
  autoCollapseMs?: number;
  /** Collapse immediately when this signal value changes to a non-zero value */
  collapseOnTick?: number;
}

export function CollapsibleSection(props: CollapsibleSectionProps) {
  const [expanded, setExpanded] = createSignal(props.expanded ?? true);
  const stopTick = useContext(StopCollapseContext);
  let userInteracted = false;
  let timerRef: number | undefined;

  // Auto-collapse timer
  const setupAutoCollapse = () => {
    if (timerRef !== undefined) clearTimeout(timerRef);
    if (props.autoCollapseMs && expanded() && !userInteracted) {
      timerRef = window.setTimeout(() => {
        if (!userInteracted) {
          setExpanded(false);
          props.onToggle?.(false);
        }
      }, props.autoCollapseMs);
    }
  };

  onMount(() => {
    setupAutoCollapse();
  });

  onCleanup(() => {
    if (timerRef !== undefined) clearTimeout(timerRef);
  });

  // Collapse when tick changes to >0 (deferred so initial tick doesn't collapse on mount)
  createEffect(
    on(
      () => props.collapseOnTick ?? 0,
      (tick) => {
        if (tick > 0 && !userInteracted && expanded()) {
          if (timerRef !== undefined) {
            clearTimeout(timerRef);
            timerRef = undefined;
          }
          setExpanded(false);
          props.onToggle?.(false);
        }
      },
      { defer: true },
    ),
  );

  // Collapse when stopTick ticks (stream end or Stop).
  // Uses Context to work across <Index>/<For> boundaries.
  createEffect(
    on(stopTick, (tick) => {
      if (tick > 0 && !userInteracted && expanded()) {
        if (timerRef !== undefined) {
          clearTimeout(timerRef);
          timerRef = undefined;
        }
        setExpanded(false);
        props.onToggle?.(false);
      }
    }),
  );

  const toggle = () => {
    if (!userInteracted) {
      userInteracted = true;
      if (timerRef !== undefined) {
        clearTimeout(timerRef);
        timerRef = undefined;
      }
    }
    const next = !expanded();
    setExpanded(next);
    props.onToggle?.(next);
  };

  return (
    <div class="mb-2">
      <button
        onClick={toggle}
        class="flex items-center gap-1.5 text-xs font-medium text-(--text-secondary) hover:text-(--accent) transition-colors cursor-pointer w-full text-left"
      >
        {props.leadingIcon}
        <span class="flex items-center gap-1">
          {props.label}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class={`h-3 w-3 mt-[2.6px] transition-transform duration-200 ${expanded() ? "rotate-90" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fill-rule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </span>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        classList={{
          "max-h-0 opacity-0": !expanded(),
          "max-h-80 opacity-100": expanded(),
        }}
      >
        <div class="mt-1">
          {props.children}
        </div>
      </div>
    </div>
  );
}
