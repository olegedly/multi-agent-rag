import { describe, it, expect } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { Sidebar } from "../Sidebar";

describe("Sidebar", () => {
  it("renders conversation list and highlights current", () => {
    const conversations = [
      { id: "1", title: "Chat A", createdAt: 200, messages: [] },
      { id: "2", title: "Chat B", createdAt: 100, messages: [] },
    ];

    render(() => (
      <Sidebar
        conversations={conversations}
        currentId="1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.getByText("Chat A")).toBeTruthy();
    expect(screen.getByText("Chat B")).toBeTruthy();
  });

  it("shows 'No conversations' when list is empty", () => {
    render(() => (
      <Sidebar
        conversations={[]}
        currentId=""
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.getByText("No conversations")).toBeTruthy();
  });
});
