import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { InboxPanel } from "./InboxPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};

const DOCS = [
  { path: "docs/adr/0001-invitation-tokens.md", kind: "concept", concept_id: "adr/0001-invitation-tokens",
    type: "Decision", title: "ADR-0001: Invitation tokens", status: "stable",
    trust_tier: "human_verified", findings: 0, commit_sha: "abc1234" },
  { path: "docs/notes/draft.md", kind: "concept", concept_id: "notes/draft", type: null,
    title: "Draft", status: null, trust_tier: "unknown", findings: 1, commit_sha: "abc1234" },
  { path: "docs/index.md", kind: "index", concept_id: null, type: null, title: "Docs",
    status: null, trust_tier: "unknown", findings: 0, commit_sha: "abc1234" },
];

const RUN = {
  id: "run-1", status: "succeeded", stage: "index", error: null,
  counts: { documents_added: 3, items_added: 2, documents_unchanged: 0 }, requests: 9,
  created_at: "2026-09-19T12:00:00Z", finished_at: "2026-09-19T12:00:05Z",
};

const DETAIL = {
  ...DOCS[0], description: "Tokens are single-use.", frontmatter: { type: "Decision" },
  body: "# Context\n\nForgeable links.\n", finding_details: [], synced_at: "2026-09-19T12:00:05Z",
};

const LINKS = [
  { source_kind: "document", source_key: "docs/adr/0001-invitation-tokens.md",
    target_kind: "document", target_key: "docs/project/product-overview.md",
    relation: "references", origin: "explicit",
    evidence: "docs/adr/0001-invitation-tokens.md: [product overview](/project/product-overview.md)",
    confidence: 1, resolved: true },
  { source_kind: "pull_request", source_key: "4",
    target_kind: "document", target_key: "docs/adr/0001-invitation-tokens.md",
    relation: "mentions", origin: "inferred",
    evidence: "PR #4 body: - docs/adr/0001-invitation-tokens.md", confidence: 0.5, resolved: true },
];

const noop = () => {};

describe("InboxPanel", () => {
  it("lists concepts with type, trust tier and findings", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/documents": () => jsonResponse(200, DOCS),
      "GET /api/workspaces/ws-2/sync-runs": () => jsonResponse(200, [RUN]),
    });
    render(<InboxPanel workspace={WORKSPACE} onOpenDocument={noop} onCloseDocument={noop} />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("ADR-0001: Invitation tokens")).toBeInTheDocument();
    expect(within(table).getByText("Human verified")).toBeInTheDocument();
    expect(within(table).getByText("No provenance")).toBeInTheDocument();
    expect(within(table).queryByText("Docs")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Show index, log and other files/));
    expect(within(table).getByText("Docs")).toBeInTheDocument();
    expect(await screen.findByText(/5 changes, 9 GitHub requests/)).toBeInTheDocument();
  });

  it("syncs and refreshes the list", async () => {
    let listed = 0;
    mockApi({
      "GET /api/workspaces/ws-2/documents": () => {
        listed += 1;
        return jsonResponse(200, listed === 1 ? [] : DOCS);
      },
      "GET /api/workspaces/ws-2/sync-runs": () => jsonResponse(200, []),
      "POST /api/workspaces/ws-2/sync": () => jsonResponse(200, RUN),
    });
    render(<InboxPanel workspace={WORKSPACE} onOpenDocument={noop} onCloseDocument={noop} />);

    expect(await screen.findByText(/Nothing synced yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    expect(await screen.findByText("ADR-0001: Invitation tokens")).toBeInTheDocument();
  });

  it("explains why a sync could not start", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/documents": () => jsonResponse(200, []),
      "GET /api/workspaces/ws-2/sync-runs": () => jsonResponse(200, []),
      "POST /api/workspaces/ws-2/sync": () =>
        jsonResponse(400, { detail: "No GitHub token configured; set ICHNOS_GITHUB_TOKEN in .env." }),
    });
    render(<InboxPanel workspace={WORKSPACE} onOpenDocument={noop} onCloseDocument={noop} />);
    fireEvent.click(await screen.findByRole("button", { name: "Sync now" }));
    expect(await screen.findByText(/No GitHub token configured/)).toBeInTheDocument();
  });

  it("shows a concept with its trust tier and links, and opens linked documents", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/documents/detail": () => jsonResponse(200, DETAIL),
      "GET /api/workspaces/ws-2/links": () => jsonResponse(200, LINKS),
    });
    const onOpen = vi.fn();
    render(
      <InboxPanel
        workspace={WORKSPACE}
        documentPath="docs/adr/0001-invitation-tokens.md"
        onOpenDocument={onOpen}
        onCloseDocument={noop}
      />,
    );

    expect(await screen.findByRole("heading", { name: "ADR-0001: Invitation tokens" })).toBeInTheDocument();
    expect(screen.getByText("Decision")).toBeInTheDocument();
    expect(screen.getByText("Human verified")).toBeInTheDocument();

    const outgoing = screen.getByRole("region", { name: "Links from this document" });
    expect(within(outgoing).getByText("explicit")).toBeInTheDocument();
    fireEvent.click(within(outgoing).getByRole("button", { name: "docs/project/product-overview.md" }));
    expect(onOpen).toHaveBeenCalledWith("docs/project/product-overview.md");

    const incoming = screen.getByRole("region", { name: "Links to this document" });
    expect(within(incoming).getByText("PR #4")).toBeInTheDocument();
    expect(within(incoming).getByText("inferred · 50%")).toBeInTheDocument();
  });

  it("searches and highlights matches", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/documents": () => jsonResponse(200, DOCS),
      "GET /api/workspaces/ws-2/sync-runs": () => jsonResponse(200, []),
      "GET /api/workspaces/ws-2/search": () =>
        jsonResponse(200, [
          { source_kind: "document", source_key: "docs/adr/0001-invitation-tokens.md",
            title: "ADR-0001: Invitation tokens", heading: "Decision",
            snippet: "Each «invitation» gets a token", start_line: 12, score: 2.1 },
          { source_kind: "issue", source_key: "2", title: "Explain invalid links",
            heading: "Scope", snippet: "«Invitation» expiry", start_line: null, score: 1.4 },
        ]),
    });
    render(<InboxPanel workspace={WORKSPACE} onOpenDocument={noop} onCloseDocument={noop} />);

    fireEvent.change(await screen.findByRole("searchbox"), { target: { value: "invitation" } });
    fireEvent.submit(screen.getByRole("search"));
    const results = await screen.findByRole("list", { name: "Results for invitation" });
    expect(within(results).getAllByText("invitation", { selector: "mark" })).toHaveLength(1);
    expect(within(results).getByText("Issue #2 · Explain invalid links")).toBeInTheDocument();
  });
});
