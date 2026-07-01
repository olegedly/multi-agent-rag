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

  it("calls onToggle with inverted value on button click", () => {
    const [expanded, setExpanded] = createSignal(true);
    const onToggle = vi.fn((next: boolean) => setExpanded(next));
    render(() => (
      <CollapsibleSection label="Results" expanded={expanded()} onToggle={onToggle}>
        <p>Content</p>
      </CollapsibleSection>
    ));
    const btn = screen.getByText("Results").closest("button")!;
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(false);
    // Click again — the parent signal has been updated
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledWith(true);
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("renders chevron rotated when expanded", () => {
    render(() => (
      <CollapsibleSection label="Results" expanded={true}>
        <p>Rotated</p>
      </CollapsibleSection>
    ));
    const btn = screen.getByText("Results").closest("button")!;
    const svg = btn.querySelector("svg")!;
    expect(svg.getAttribute("class")).toContain("rotate-90");
  });

  it("renders chevron not rotated when collapsed", () => {
    render(() => (
      <CollapsibleSection label="Results" expanded={false}>
        <p>Not rotated</p>
      </CollapsibleSection>
    ));
    const btn = screen.getByText("Results").closest("button")!;
    const svg = btn.querySelector("svg")!;
    expect(svg.getAttribute("class")).not.toContain("rotate-90");
  });
});
