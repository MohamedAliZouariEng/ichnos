import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { QuestionsPanel } from "./QuestionsPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const ANSWER = {
  id: "an-1",
  question: "What approved evidence shows that invitation links must expire?",
  statements: [{ text: "The meeting decided that links expire after 7 days.", cites: ["S8"] }],
  gaps: ["No passing test was found among the sources."],
  cited: ["S8"],
  trail: [{ label: "Workspace onboarding sync", url: "https://github.com/o/r/blob/c/docs/meetings/note.md" }],
  sources: [
    { id: "S8", kind: "document", title: "Workspace onboarding sync",
      locator: "docs/meetings/note.md#decisions", url: "https://github.com/o/r/blob/c/docs/meetings/note.md#decisions",
      trust: "human_verified", flags: [], excerpt: "Decision." },
    { id: "S9", kind: "issue", title: "Default expiry", locator: "#7", url: "https://github.com/o/r/issues/7",
      trust: "github", flags: [], excerpt: "Story." },
  ],
  model: "ichnos/gemini-3.8-flash",
  tokens: 2914,
  created_at: "2026-09-20T12:00:00Z",
};

describe("QuestionsPanel", () => {
  it("asks, then shows cited statements as links, gaps and sources", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/questions": () => jsonResponse(200, []),
      "POST /api/workspaces/ws-2/questions": () => jsonResponse(201, ANSWER),
    });
    const onOpenAnswer = vi.fn();
    render(<QuestionsPanel workspace={WORKSPACE} onOpenAnswer={onOpenAnswer} />);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: ANSWER.question } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const statements = await screen.findByRole("region", { name: "Statements" });
    expect(within(statements).getByRole("link", { name: "S8" })).toHaveAttribute(
      "href", "https://github.com/o/r/blob/c/docs/meetings/note.md#decisions",
    );
    expect(within(screen.getByRole("region", { name: "Gaps" })).getByText(/No passing test/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Sources" })).getByText("cited")).toBeInTheDocument();
    const trail = screen.getByRole("region", { name: "Evidence trail" });
    expect(within(trail).getByRole("link", { name: "Workspace onboarding sync" })).toBeInTheDocument();
    expect(onOpenAnswer).toHaveBeenCalledWith("an-1");
  });

  it("reopens an earlier answer", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/questions": () =>
        jsonResponse(200, [{ id: "an-1", question: ANSWER.question, statements: 1, gaps: 1, created_at: ANSWER.created_at }]),
      "GET /api/answers/an-1": () => jsonResponse(200, ANSWER),
    });
    render(<QuestionsPanel workspace={WORKSPACE} answerId="an-1" onOpenAnswer={() => {}} />);
    expect(await screen.findByRole("heading", { name: ANSWER.question })).toBeInTheDocument();
    expect(screen.getByText("1 statements · 1 gaps")).toBeInTheDocument();
  });
});
