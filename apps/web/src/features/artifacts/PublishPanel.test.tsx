import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { PublishPanel } from "./PublishPanel";

const ARTIFACT = {
  id: "art-1", workspace_id: "ws-2", kind: "brd", title: "Invitation expiry", slug: "x",
  path: "docs/specs/x/brd.md", status: "draft", current_version: 2, run_id: "run-1",
  created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z", findings: 0,
  source_ids: [], versions: [],
  current: {
    number: 2, origin: "edited", actor: "human:octo", parent_number: 1, note: null,
    created_at: "2026-09-19T12:00:00Z", findings: 0, content: "---\ntype: BRD\n---\n", finding_details: [],
  },
};

describe("PublishPanel", () => {
  it("publishes a draft and opens the approval", async () => {
    mockApi({ "POST /api/artifacts/art-1/publish": () => jsonResponse(201, { id: "ap-1" }) });
    const onOpenApproval = vi.fn();
    render(<PublishPanel artifact={ARTIFACT} onOpenApproval={onOpenApproval} />);
    fireEvent.click(screen.getByRole("button", { name: "Publish…" }));
    await vi.waitFor(() => expect(onOpenApproval).toHaveBeenCalledWith("ap-1"));
  });

  it("explains why publishing could not start", async () => {
    mockApi({
      "POST /api/artifacts/art-1/publish": () => jsonResponse(401, { detail: "Sign in to approve." }),
    });
    render(<PublishPanel artifact={ARTIFACT} />);
    fireEvent.click(screen.getByRole("button", { name: "Publish…" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in to approve.");
  });

  it("plans an approved BRD and opens the run", async () => {
    mockApi({ "POST /api/artifacts/art-1/plan": () => jsonResponse(202, { id: "run-9" }) });
    const onOpenRun = vi.fn();
    render(<PublishPanel artifact={{ ...ARTIFACT, status: "approved" }} onOpenRun={onOpenRun} />);
    fireEvent.click(screen.getByRole("button", { name: "Plan Epic and Stories" }));
    await vi.waitFor(() => expect(onOpenRun).toHaveBeenCalledWith("run-9"));
  });

  it("says when a publish action is waiting", () => {
    render(<PublishPanel artifact={{ ...ARTIFACT, status: "needs-review" }} />);
    expect(screen.getByText("A publish action is waiting in Approvals.")).toBeInTheDocument();
  });
});

const PLAN = {
  ...ARTIFACT,
  kind: "implementation-plan",
  current: {
    ...ARTIFACT.current,
    content:
      "# Implementation plan: Story #7, X\n\n## Proposed decisions\n\n" +
      "### Expire from creation\n\n**Decision.** Expire after 7 days.\n",
  },
};

describe("Plan actions", () => {
  it("proposes the draft pull request and publishes a decision", async () => {
    mockApi({
      "POST /api/artifacts/art-1/draft-pull-request": () => jsonResponse(201, { id: "ap-7" }),
      "POST /api/artifacts/art-1/decisions": () => jsonResponse(201, { id: "ap-8" }),
    });
    const onOpenApproval = vi.fn();
    render(<PublishPanel artifact={PLAN} onOpenApproval={onOpenApproval} />);
    expect(screen.queryByRole("button", { name: "Publish…" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open draft PR…" }));
    await vi.waitFor(() => expect(onOpenApproval).toHaveBeenCalledWith("ap-7"));
    fireEvent.click(screen.getByRole("button", { name: "Publish decision: Expire from creation…" }));
    await vi.waitFor(() => expect(onOpenApproval).toHaveBeenCalledWith("ap-8"));
  });
});
