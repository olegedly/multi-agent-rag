import {
  createSignal,
  createEffect,
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
  /**
   * When this value changes, the auto-collapse timer resets.
   * Used during streaming: pass the tool result content so the timer
   * restarts each time a new chunk arrives.
   */
  resetTimerOn?: unknown;
  /**
   * When true, the stop-tick context (stream-end / Stop button) will
   * NOT collapse this section.  Used by ToolResultPartRenderer which
   * wants only the autoCollapseMs timer, not an immediate collapse.
   */
  disableStopCollapse?: boolean;
}

export function CollapsibleSection(props: CollapsibleSectionProps) {
  const [expanded, setExpanded] = createSignal(props.expanded ?? true);
  const stopTick = useContext(StopCollapseContext);
  let userInteracted = false;
  let timerRef: number | undefined;

  // Auto-collapse timer — resets whenever children content changes,
  // so streaming updates extend the visible window via the
  // resetTimerOn prop (passed from the parent on content update).
  const setupAutoCollapse = () => {
    if (timerRef !== undefined) {
      clearTimeout(timerRef);
      timerRef = undefined;
    }
    if (props.autoCollapseMs && expanded() && !userInteracted) {
      timerRef = window.setTimeout(() => {
        if (!userInteracted) {
          setExpanded(false);
          props.onToggle?.(false);
        }
      }, props.autoCollapseMs);
    }
  };

  // Start the timer on mount and reset it whenever streaming content updates.
  // The resetTimerOn prop changes each time new content arrives, causing
  // setupAutoCollapse to clear the old timer and start a fresh one.
  createEffect(
    on(
      () => props.resetTimerOn,
      () => {
        setupAutoCollapse();
      },
      { defer: false },
    ),
  );

  onCleanup(() => {
    if (timerRef !== undefined) {
      clearTimeout(timerRef);
      timerRef = undefined;
    }
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

  // Collapse when stopTick ticks (stream end or Stop), unless
  // this section has opted out (e.g. tool results use autoCollapseMs).
  createEffect(
    on(stopTick, (tick) => {
      if (props.disableStopCollapse) return;
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
    <div>
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
