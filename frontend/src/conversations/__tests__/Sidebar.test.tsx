import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { Sidebar } from "../Sidebar";

function makeConvs(corpusId: string = "corpus-1") {
  return [
    { id: "1", corpusId, title: "Chat A", createdAt: 200, updatedAt: 200, messages: [] },
    { id: "2", corpusId, title: "Chat B", createdAt: 100, updatedAt: 100, messages: [] },
  ];
}

function click(el: Element | null) {
  if (!el) throw new Error("Cannot click null element");
  fireEvent.click(el);
}

describe("Sidebar", () => {
  it("renders conversation list and highlights current", () => {
    const conversations = makeConvs();

    render(() => (
      <Sidebar
        conversations={conversations}
        currentId="1"
        activeCorpusId="corpus-1"
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
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.getByText("No conversations")).toBeTruthy();
  });

  it("calls onNew when New button is clicked", () => {
    const onNew = vi.fn();
    render(() => (
      <Sidebar
        conversations={[]}
        currentId=""
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={onNew}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    click(screen.getByText("+ New"));
    expect(onNew).toHaveBeenCalledOnce();
  });

  it("calls onSelect when a conversation is clicked", () => {
    const onSelect = vi.fn();
    render(() => (
      <Sidebar
        conversations={makeConvs()}
        currentId="1"
        activeCorpusId="corpus-1"
        onSelect={onSelect}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    click(screen.getByText("Chat B"));
    expect(onSelect).toHaveBeenCalledWith("2");
  });

  it("shows a trash (delete) button per conversation row on initial render", () => {
    render(() => (
      <Sidebar
        conversations={makeConvs()}
        currentId="1"
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    const deleteBtns = screen.getAllByTitle("Delete conversation");
    expect(deleteBtns.length).toBe(2);
  });

  it("does not show confirm/cancel buttons on initial render", () => {
    render(() => (
      <Sidebar
        conversations={makeConvs()}
        currentId="1"
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.queryByTitle("Confirm delete")).toBeNull();
    expect(screen.queryByTitle("Cancel delete")).toBeNull();
  });

  it("has a header with title and new-conversation button", () => {
    render(() => (
      <Sidebar
        conversations={makeConvs()}
        currentId="1"
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.getByText("Conversations")).toBeTruthy();
    expect(screen.getByText("+ New")).toBeTruthy();
  });

  it("filters conversations to only those matching activeCorpusId", () => {
    const conversations = [
      ...makeConvs("corpus-1"),
      { id: "3", corpusId: "corpus-2", title: "Other Corpus", createdAt: 50, updatedAt: 50, messages: [] },
    ];
    render(() => (
      <Sidebar
        conversations={conversations}
        currentId="1"
        activeCorpusId="corpus-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
        isOpen={true}
        onClose={() => {}}
      />
    ));

    expect(screen.queryByText("Chat A")).toBeTruthy();
    expect(screen.queryByText("Chat B")).toBeTruthy();
    expect(screen.queryByText("Other Corpus")).toBeNull();
  });
});
