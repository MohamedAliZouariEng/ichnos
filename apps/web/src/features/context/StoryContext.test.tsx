import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { StoryContext } from "./StoryContext";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const item = (id: string, role: string, title: string, trust: string, flags: string[] = []) => ({
  id, role, title, trust, flags, source: `${title}@abcdef12`, url: null,
  reason: `because of ${role}`, excerpt: `text of ${title}`,
});
const PACK = {
  story: 7,
  items: [
    { ...item("P1", "story", "Default invitation expiry", "github"), url: "https://github.com/o/r/issues/7" },
    item("P2", "epic", "Invitation lifecycle", "github"),
    item("P3", "brd", "docs/specs/x/brd.md", "human_verified"),
    item("P4", "adr", "ADR-0009", "generated", ["unverified", "stale"]),
    item("P5", "code", "src/quire/invitations/service.py", "repository"),
  ],
  absent: ["initiative", "techspec"],
  keywords: ["invitation"],
  hash: "f".repeat(64),
  notes: [],
};

describe("StoryContext", () => {
  it("groups the pack by role with trust, flags and what is absent", async () => {
    mockApi({ "GET /api/workspaces/ws-2/stories/7/context": () => jsonResponse(200, PACK) });
    render(<StoryContext workspace={WORKSPACE} number={7} onBack={() => {}} />);
    expect(await screen.findByRole("heading", { name: "Story #7: Default invitation expiry" })).toBeInTheDocument();
    expect(screen.getByText("Not found for this Story: initiative, techspec.")).toBeInTheDocument();
    const decisions = screen.getByRole("region", { name: "Decisions" });
    expect(within(decisions).getByText("unverified")).toBeInTheDocument();
    expect(within(decisions).getByText("stale")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Business requirements" })).getByText("Human verified"))
      .toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Code" })).getByText("Excerpt")).toBeInTheDocument();
  });

  it("explains a Story that cannot be packed", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/stories/99/context": () =>
        jsonResponse(404, { detail: "Issue #99 is not synced in this workspace." }),
    });
    render(<StoryContext workspace={WORKSPACE} number={99} onBack={() => {}} />);
    expect(await screen.findByText("Issue #99 is not synced in this workspace.")).toBeInTheDocument();
  });
});

describe("Planning a Story", () => {
  it("starts a planning run and opens it", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/stories/7/context": () => jsonResponse(200, PACK),
      "POST /api/workspaces/ws-2/stories/7/plan": () => jsonResponse(202, { id: "run-5" }),
    });
    const onOpenRun = vi.fn();
    render(<StoryContext workspace={WORKSPACE} number={7} onBack={() => {}} onOpenRun={onOpenRun} />);
    expect(await screen.findByText(/including code, to the configured model/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Plan this Story" }));
    await vi.waitFor(() => expect(onOpenRun).toHaveBeenCalledWith("run-5"));
  });
});
