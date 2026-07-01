import { describe, it, expect, vi } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { createCollapseState } from "../collapse";

/** Helper: flush Solid's reactive microtasks so effects run. */
async function flush(): Promise<void> {
  await new Promise((r) => queueMicrotask(r));
  await new Promise((r) => setTimeout(r, 0));
}

describe("createCollapseState", () => {
  it("starts expanded when initiallyExpanded is true", () => {
    createRoot(() => {
      const state = createCollapseState({ initiallyExpanded: true });
      expect(state.expanded()).toBe(true);
    });
  });

  it("starts collapsed when initiallyExpanded is false", () => {
    createRoot(() => {
      const state = createCollapseState({ initiallyExpanded: false });
      expect(state.expanded()).toBe(false);
    });
  });

  it("toggles expanded state on each call to toggle()", () => {
    createRoot(() => {
      const state = createCollapseState({ initiallyExpanded: true });
      expect(state.expanded()).toBe(true);
      state.toggle();
      expect(state.expanded()).toBe(false);
      state.toggle();
      expect(state.expanded()).toBe(true);
    });
  });

  it("calls onToggle with new expanded value when toggle() is called", () => {
    createRoot(() => {
      const onToggle = vi.fn();
      const state = createCollapseState({ initiallyExpanded: true, onToggle });
      state.toggle();
      expect(onToggle).toHaveBeenCalledWith(false);
      state.toggle();
      expect(onToggle).toHaveBeenCalledWith(true);
      expect(onToggle).toHaveBeenCalledTimes(2);
    });
  });

  it("auto-collapses after autoCollapseMs when user has not interacted", () => {
    vi.useFakeTimers();
    createRoot(() => {
      const state = createCollapseState({
        initiallyExpanded: true,
        autoCollapseMs: 500,
      });
      expect(state.expanded()).toBe(true);
      vi.advanceTimersByTime(600);
      expect(state.expanded()).toBe(false);
    });
    vi.useRealTimers();
  });

  it("does NOT auto-collapse after user interacts (toggles)", () => {
    vi.useFakeTimers();
    createRoot(() => {
      const state = createCollapseState({
        initiallyExpanded: true,
        autoCollapseMs: 500,
      });
      expect(state.expanded()).toBe(true);
      // Toggle (collapse then re-expand) disables auto-collapse
      state.toggle();
      state.toggle();
      expect(state.expanded()).toBe(true);
      vi.advanceTimersByTime(600);
      // Should still be expanded — user interacted
      expect(state.expanded()).toBe(true);
    });
    vi.useRealTimers();
  });

  it("resets auto-collapse timer when resetOn value changes (streaming update)", async () => {
    vi.useFakeTimers();
    const [content, setContent] = createSignal("First chunk");

    let capturedState: { expanded: () => boolean } | undefined;
    const dispose = createRoot((rootDispose) => {
      const state = createCollapseState({
        initiallyExpanded: true,
        autoCollapseMs: 500,
        resetOn: content,
      });
      capturedState = state;
      return rootDispose;
    });

    expect(capturedState!.expanded()).toBe(true);
    // Advance to just before original timeout
    await vi.advanceTimersByTimeAsync(400);

    // Content updates (simulating new streamed chunk arriving)
    setContent("Second chunk");
    // Use advanceTimersByTimeAsync(0) to flush microtasks under fake timers
    await vi.advanceTimersByTimeAsync(0);

    // Advance past original deadline — should still be expanded if timer was reset
    await vi.advanceTimersByTimeAsync(200); // 600ms total, past original 500ms deadline
    expect(capturedState!.expanded()).toBe(true);

    // Advance past the new deadline (500ms after update)
    await vi.advanceTimersByTimeAsync(400); // 1000ms total
    expect(capturedState!.expanded()).toBe(false);

    vi.useRealTimers();
    dispose();
  });

  it("cleans up timer on dispose", () => {
    vi.useFakeTimers();
    const dispose = createRoot((rootDispose) => {
      createCollapseState({
        initiallyExpanded: true,
        autoCollapseMs: 500,
      });
      return rootDispose;
    });
    dispose();
    // Advancing should not throw (timer was cleared)
    expect(() => vi.advanceTimersByTime(600)).not.toThrow();
    vi.useRealTimers();
  });

  it("collapses immediately when collapseOnTick changes to >0", async () => {
    const [tick, setTick] = createSignal(0);
    let capturedState: { expanded: () => boolean } | undefined;
    const dispose = createRoot((rootDispose) => {
      const state = createCollapseState({
        initiallyExpanded: true,
        collapseOnTick: tick,
      });
      capturedState = state;
      return rootDispose;
    });

    expect(capturedState!.expanded()).toBe(true);
    setTick(1);
    await flush();
    expect(capturedState!.expanded()).toBe(false);
    dispose();
  });

  it("does NOT collapse on tick=0 (deferred initial value)", async () => {
    const [tick] = createSignal(0);
    let capturedState: { expanded: () => boolean } | undefined;
    const dispose = createRoot((rootDispose) => {
      const state = createCollapseState({
        initiallyExpanded: true,
        collapseOnTick: tick,
      });
      capturedState = state;
      return rootDispose;
    });

    // Tick is 0 at mount, defer skips it — should remain expanded
    await flush();
    expect(capturedState!.expanded()).toBe(true);
    dispose();
  });

  it("collapses on stopTick when it changes to >0", async () => {
    const [stopTick, setStopTick] = createSignal(0);
    let capturedState: { expanded: () => boolean } | undefined;
    const dispose = createRoot((rootDispose) => {
      const state = createCollapseState({
        initiallyExpanded: true,
        stopTick: stopTick,
      });
      capturedState = state;
      return rootDispose;
    });

    expect(capturedState!.expanded()).toBe(true);
    setStopTick(1);
    await flush();
    expect(capturedState!.expanded()).toBe(false);
    dispose();
  });

  it("does NOT collapse on stopTick when disableStopCollapse is true", async () => {
    const [stopTick, setStopTick] = createSignal(0);
    let capturedState: { expanded: () => boolean } | undefined;
    const dispose = createRoot((rootDispose) => {
      const state = createCollapseState({
        initiallyExpanded: true,
        stopTick: stopTick,
        disableStopCollapse: true,
      });
      capturedState = state;
      return rootDispose;
    });

    setStopTick(1);
    await flush();
    expect(capturedState!.expanded()).toBe(true);
    dispose();
  });

  it("calls onToggle when collapsing via collapseOnTick", async () => {
    const [tick, setTick] = createSignal(0);
    const onToggle = vi.fn();
    const dispose = createRoot((rootDispose) => {
      createCollapseState({
        initiallyExpanded: true,
        collapseOnTick: tick,
        onToggle,
      });
      return rootDispose;
    });

    setTick(1);
    await flush();
    expect(onToggle).toHaveBeenCalledWith(false);
    dispose();
  });
});
