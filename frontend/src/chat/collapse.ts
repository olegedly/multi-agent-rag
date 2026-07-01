import {
  createSignal,
  createEffect,
  onCleanup,
  on,
} from "solid-js";

export interface CollapseConfig {
  initiallyExpanded: boolean;
  onToggle?: (expanded: boolean) => void;
  /** Auto-collapse after this many ms when user hasn't interacted */
  autoCollapseMs?: number;
  /**
   * Accessor whose tracked value resets the auto-collapse timer when it changes.
   * Pass the raw accessor (not the dereferenced value) so the hook can track it.
   */
  resetOn?: () => unknown;
  /**
   * Accessor returning a tick value. Collapses when it changes to >0.
   * Pass the raw accessor so it's tracked reactively.
   */
  collapseOnTick?: () => number;
  /**
   * Accessor returning a tick value. Collapses on change to >0, unless disabled.
   * Pass the raw accessor so it's tracked reactively.
   */
  stopTick?: () => number;
  /** When true, the stopTick trigger is ignored */
  disableStopCollapse?: boolean;
}

export interface CollapseState {
  expanded(): boolean;
  toggle(): void;
}

export function createCollapseState(config: CollapseConfig): CollapseState {
  const [expanded, setExpanded] = createSignal(config.initiallyExpanded);
  let userInteracted = false;
  let timerRef: number | undefined;

  const clearTimer = () => {
    if (timerRef !== undefined) {
      clearTimeout(timerRef);
      timerRef = undefined;
    }
  };

  const startAutoCollapse = () => {
    clearTimer();
    if (config.autoCollapseMs && expanded() && !userInteracted) {
      timerRef = window.setTimeout(() => {
        if (!userInteracted) {
          setExpanded(false);
          config.onToggle?.(false);
        }
      }, config.autoCollapseMs);
    }
  };

  const collapse = () => {
    if (!userInteracted && expanded()) {
      clearTimer();
      setExpanded(false);
      config.onToggle?.(false);
    }
  };

  // Start the timer on first creation
  startAutoCollapse();

  // Reset timer whenever resetOn value changes (streaming content update)
  if (config.resetOn) {
    createEffect(
      on(
        () => config.resetOn?.(),
        () => {
          startAutoCollapse();
        },
        { defer: false },
      ),
    );
  }

  // Collapse when collapseOnTick changes to >0 (deferred: skip initial tick=0)
  if (config.collapseOnTick) {
    createEffect(
      on(
        config.collapseOnTick,
        (tick) => {
          if (tick > 0) collapse();
        },
        { defer: true },
      ),
    );
  }

  // Collapse when stopTick changes to >0 (unless disabled)
  if (config.stopTick && !config.disableStopCollapse) {
    createEffect(
      on(config.stopTick, (tick) => {
        if (tick > 0) collapse();
      }),
    );
  }

  onCleanup(clearTimer);

  const toggle = () => {
    if (!userInteracted) {
      userInteracted = true;
      clearTimer();
    }
    const next = !expanded();
    setExpanded(next);
    config.onToggle?.(next);
  };

  return { expanded, toggle };
}
