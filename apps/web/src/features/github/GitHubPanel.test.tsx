import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { GitHubPanel } from "./GitHubPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};

const ITEMS = [
  { number: 4, type: "pull_request", title: "Add onboarding glossary", state: "closed",
    author: "alice", labels: [], url: "https://github.com/o/r/pull/4",
    updated_at: "2026-09-19T12:00:00Z", merged_at: "2026-09-19T12:00:00Z" },
  { number: 2, type: "issue", title: "Explain invalid invitation links", state: "open",
    author: "alice", labels: ["type:story", "status:draft"], url: "https://github.com/o/r/issues/2",
    updated_at: "2026-09-19T11:00:00Z", merged_at: null },
];

const STORY_LINKS = [
  { source_kind: "issue", source_key: "2", target_kind: "issue", target_key: "1",
    relation: "parent", origin: "explicit", evidence: "Issue #2 body: - Epic: #1",
    confidence: 1, resolved: true },
  { source_kind: "issue", source_key: "2", target_kind: "document",
    target_key: "docs/meetings/2026-09-15-workspace-onboarding.md", relation: "references",
    origin: "explicit", evidence: "Issue #2 body: - docs/meetings/…", confidence: 1, resolved: true },
];

describe("GitHubPanel", () => {
  it("lists Issues and pull requests with state and labels, and filters them", async () => {
    mockApi({ "GET /api/workspaces/ws-2/github/items": () => jsonResponse(200, ITEMS) });
    render(<GitHubPanel workspace={WORKSPACE} onOpenDocument={() => {}} />);

    expect(await screen.findByText("Add onboarding glossary")).toBeInTheDocument();
    expect(screen.getByText("merged")).toBeInTheDocument();
    expect(screen.getByText("type:story")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pull requests" }));
    expect(screen.queryByText("Explain invalid invitation links")).not.toBeInTheDocument();
    expect(screen.getByText("Add onboarding glossary")).toBeInTheDocument();
  });

  it("shows an item's links and opens linked documents in the Inbox", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/github/items": () => jsonResponse(200, ITEMS),
      "GET /api/workspaces/ws-2/links": () => jsonResponse(200, STORY_LINKS),
    });
    const onOpen = vi.fn();
    render(<GitHubPanel workspace={WORKSPACE} onOpenDocument={onOpen} />);

    const story = (await screen.findByText("Explain invalid invitation links")).closest("li");
    expect(story).not.toBeNull();
    fireEvent.click(within(story as HTMLElement).getByRole("button", { name: "Show links" }));

    const outgoing = await screen.findByRole("region", { name: "Links from #2" });
    expect(within(outgoing).getByText("Issue #1")).toBeInTheDocument();
    fireEvent.click(
      within(outgoing).getByRole("button", {
        name: "docs/meetings/2026-09-15-workspace-onboarding.md",
      }),
    );
    expect(onOpen).toHaveBeenCalledWith("docs/meetings/2026-09-15-workspace-onboarding.md");
  });

  it("explains what to do when nothing is synced", async () => {
    mockApi({ "GET /api/workspaces/ws-2/github/items": () => jsonResponse(200, []) });
    render(<GitHubPanel workspace={WORKSPACE} onOpenDocument={() => {}} />);
    expect(await screen.findByText(/No Issues or pull requests synced yet/)).toBeInTheDocument();
  });
});
