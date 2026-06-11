import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { CollapsibleSection } from "../CollapsibleSection";

describe("CollapsibleSection", () => {
  it("renders label and children", () => {
    render(() => (
      <CollapsibleSection label="Results">
        <p>Content here</p>
      </CollapsibleSection>
    ));
    expect(screen.getByText("Results")).toBeTruthy();
    expect(screen.getByText("Content here")).toBeTruthy();
  });

  it("shows children when expanded (default)", () => {
    render(() => (
      <CollapsibleSection label="Results">
        <p>Visible content</p>
      </CollapsibleSection>
    ));
    const wrapper = screen.getByText("Visible content").closest('[class*="overflow-hidden"]')!;
    // expanded = no max-h-0 or opacity-0
    expect(wrapper.className).not.toContain("max-h-0");
    expect(wrapper.className).not.toContain("opacity-0");
  });

  it("hides children when collapsed", () => {
    render(() => (
      <CollapsibleSection label="Results" expanded={false}>
        <p>Hidden content</p>
      </CollapsibleSection>
    ));
    const wrapper = screen.getByText("Hidden content").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).toContain("max-h-0");
    expect(wrapper.className).toContain("opacity-0");
  });

  it("toggles expanded state on button click", () => {
    render(() => (
      <CollapsibleSection label="Results">
        <p>Toggle me</p>
      </CollapsibleSection>
    ));

    const btn = screen.getByText("Results").closest("button")!;
    // Initially expanded, click to collapse
    fireEvent.click(btn);
    const wrapper = screen.getByText("Toggle me").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).toContain("opacity-0");

    // Click again to expand
    fireEvent.click(btn);
    expect(wrapper.className).not.toContain("opacity-0");
  });

  it("calls onToggle when provided", () => {
    const onToggle = vi.fn();
    render(() => (
      <CollapsibleSection label="Results" onToggle={onToggle}>
        <p>Content</p>
      </CollapsibleSection>
    ));

    const btn = screen.getByText("Results").closest("button")!;
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(false); // was true, now false
  });

  it("auto-collapses after autoCollapseMs when user has not interacted", () => {
    vi.useFakeTimers();
    render(() => (
      <CollapsibleSection label="Results" autoCollapseMs={500}>
        <p>Auto-collapsing</p>
      </CollapsibleSection>
    ));

    // Initially expanded
    const wrapper = screen.getByText("Auto-collapsing").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).not.toContain("opacity-0");

    // Advance past timeout
    vi.advanceTimersByTime(600);
    expect(wrapper.className).toContain("opacity-0");

    vi.useRealTimers();
  });

  it("does NOT auto-collapse after user interacts (toggles)", () => {
    vi.useFakeTimers();
    render(() => (
      <CollapsibleSection label="Results" autoCollapseMs={500}>
        <p>Keep visible</p>
      </CollapsibleSection>
    ));

    const btn = screen.getByText("Results").closest("button")!;
    fireEvent.click(btn); // collapse
    fireEvent.click(btn); // re-expand

    vi.advanceTimersByTime(600);

    // Should still be expanded — user interacted
    const wrapper = screen.getByText("Keep visible").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).not.toContain("opacity-0");

    vi.useRealTimers();
  });

  it("collapses immediately when collapseOnTick signal changes", () => {
    const [tick, setTick] = createSignal(0);
    render(() => (
      <CollapsibleSection label="Results" collapseOnTick={tick()}>
        <p>Collapse on tick</p>
      </CollapsibleSection>
    ));

    // Initially expanded (tick=0, defer skips)
    const wrapper = screen.getByText("Collapse on tick").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).not.toContain("opacity-0");

    // Change tick to 1 — should collapse
    setTick(1);
    queueMicrotask(() => {
      expect(wrapper.className).toContain("opacity-0");
    });
  });

  it("does not collapse on tick 0 (initial value, defer)", () => {
    render(() => (
      <CollapsibleSection label="Results" collapseOnTick={0}>
        <p>No collapse on 0</p>
      </CollapsibleSection>
    ));

    const wrapper = screen.getByText("No collapse on 0").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).not.toContain("opacity-0");
  });

  it("cleans up timer on unmount", () => {
    vi.useFakeTimers();
    const { unmount } = render(() => (
      <CollapsibleSection label="Results" autoCollapseMs={500}>
        <p>Timer cleanup</p>
      </CollapsibleSection>
    ));

    unmount();
    // Advancing should not throw (timer was cleared)
    vi.advanceTimersByTime(600);
    vi.useRealTimers();
  });
});
