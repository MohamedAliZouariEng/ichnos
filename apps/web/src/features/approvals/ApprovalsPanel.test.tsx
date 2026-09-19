import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { ApprovalsPanel } from "./ApprovalsPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const SIGNED_IN = {
  approvals_enabled: true, signed_in: true, approver: "human:MohamedAliZouariEng",
  expires_at: "2026-09-20T06:00:00Z",
};
const SUMMARY = {
  id: "ap-1", workspace_id: "ws-2", run_id: "run-1", artifact_id: "art-1",
  action_type: "docs_pull_request", target: "MohamedAliZouariEng/quire-demo", branch: "main",
  summary: "Publish BRD: Invitation expiry", status: "pending", payload_hash: "a".repeat(64),
  proposed_by: "human:MohamedAliZouariEng", decided_by: null, decided_at: null,
  decision_note: null, created_at: "2026-09-19T12:00:00Z", executed_at: null, error: null,
  result: null,
};
const DOCS = {
  ...SUMMARY,
  hash_ok: true,
  base: { files: { "docs/specs/x/brd.md": null, "docs/specs/index.md": "abc" } },
  payload: {
    kind: "docs_pull_request", approver: "human:MohamedAliZouariEng", branch: "ichnos/x-v2",
    base_branch: "main", title: "Publish BRD: Invitation expiry", body: "Publishes the BRD.",
    files: [
      { path: "docs/specs/x/brd.md", content: "---\ntype: BRD\nstatus: stable\n---\n" },
      { path: "docs/specs/index.md", content: "# Specifications\n" },
    ],
  },
};
const ISSUES = {
  ...SUMMARY,
  id: "ap-2", action_type: "create_issues", summary: "Create 1 Epic and 1 Stories", hash_ok: true,
  base: {},
  payload: {
    kind: "create_issues", approver: "human:MohamedAliZouariEng",
    epic: { title: "Invitation lifecycle", body: "Harden invitations.", labels: ["type:epic"] },
    stories: [
      { key: "S-1", title: "Expire invitations", body: "## Parent\n- Epic: #{epic}\n", labels: ["type:story"] },
    ],
  },
};
const noop = () => {};

function review(detail: object, extra: Record<string, () => Response> = {}, session = SIGNED_IN) {
  mockApi({
    "GET /api/session": () => jsonResponse(200, session),
    [`GET /api/approvals/${(detail as { id: string }).id}`]: () => jsonResponse(200, detail),
    ...extra,
  });
  render(
    <ApprovalsPanel
      workspace={WORKSPACE}
      approvalId={(detail as { id: string }).id}
      onOpenApproval={noop}
      onCloseApproval={noop}
    />,
  );
}

describe("ApprovalsPanel", () => {
  it("lists actions waiting for approval", async () => {
    mockApi({ "GET /api/workspaces/ws-2/approvals": () => jsonResponse(200, [SUMMARY]) });
    const onOpen = vi.fn();
    render(<ApprovalsPanel workspace={WORKSPACE} onOpenApproval={onOpen} onCloseApproval={noop} />);
    fireEvent.click(await screen.findByRole("button", { name: "Publish BRD: Invitation expiry" }));
    expect(onOpen).toHaveBeenCalledWith("ap-1");
    expect(screen.getByText("Docs pull request")).toBeInTheDocument();
  });

  it("shows every file and approves only after confirmation", async () => {
    const executed = {
      ...DOCS, status: "executed",
      result: { pull_request: { number: 7, url: "https://github.com/o/r/pull/7" } },
    };
    review(DOCS, { "POST /api/approvals/ap-1/approve": () => jsonResponse(200, executed) });

    const files = await screen.findByRole("region", { name: "Files" });
    expect(within(files).getByText("new file")).toBeInTheDocument();
    expect(within(files).getByText("changes an existing file")).toBeInTheDocument();
    expect(screen.getByText("hash verified")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve…" }));
    const confirm = screen.getByRole("button", { name: "Confirm and write to GitHub" });
    expect(confirm).toHaveFocus();
    fireEvent.click(confirm);
    expect(await screen.findByRole("link", { name: "#7" })).toHaveAttribute("href", "https://github.com/o/r/pull/7");
  });

  it("cancels a confirmation with Escape", async () => {
    review(DOCS);
    fireEvent.click(await screen.findByRole("button", { name: "Approve…" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Confirm and write to GitHub" }), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Approve…" })).toBeInTheDocument();
  });

  it("shows Issues with their placeholders and rejects with a note", async () => {
    review(ISSUES, {
      "POST /api/approvals/ap-2/reject": () =>
        jsonResponse(200, { ...ISSUES, status: "rejected", decision_note: "Too big" }),
    });
    const issues = await screen.findByRole("region", { name: "Issues" });
    expect(within(issues).getByText("Epic: Invitation lifecycle")).toBeInTheDocument();
    expect(within(issues).getByText("S-1: Expire invitations")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Reject with a note (optional)"), { target: { value: "Too big" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByText("Rejected: Too big")).toBeInTheDocument();
  });

  it("asks to sign in before deciding", async () => {
    review(DOCS, {}, { ...SIGNED_IN, signed_in: false, approver: null } as never);
    expect(await screen.findByText(/Sign in to approve/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve…" })).not.toBeInTheDocument();
  });
});
