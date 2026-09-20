import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { TracePanel } from "./TracePanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const BRD = "docs/specs/x/brd.md";
const row = (id: string, level: string, key: string, status: string, children: object[] = [], evidence: object[] = []) =>
  ({ id, level, key, title: `${key} title`, status, url: null, evidence, children });
const inferred = (confirmed: boolean) => ({
  text: "test file modified in PR #20", source: "Pull request #20", url: null,
  origin: "inferred", link: "pull_request:20->file:tests/t.py", confirmed,
});
const trace = (confirmed: boolean) => ({
  brd: BRD, title: "X", hash: "f".repeat(64),
  rows: [row("T1", "requirement", "R-01", "approved", [
    row("T2", "epic", "#6", "open", [row("T3", "story", "#7", "open", [
      row("T4", "criterion", "AC-01", "not started"),
      row("T5", "pull_request", "PR #20", "merged", [row("T6", "test", "tests/t.py", "passing", [], [inferred(confirmed)])]),
    ])]),
  ])],
  findings: [
    { code: "criterion-without-test", level: "warning", row: "T4", message: "AC-01 has no test evidence yet." },
    ...(confirmed ? [] : [{ code: "inferred-unconfirmed", level: "warning", row: "T6", message: "tests/t.py was linked by inference." }]),
  ],
});
const SIGNED_IN = { approvals_enabled: true, signed_in: true, approver: "human:octo", expires_at: "2026-09-21T00:00:00Z" };

describe("TracePanel", () => {
  it("shows the tree with statuses and the findings under their rows", async () => {
    mockApi({
      "GET /api/workspaces/ws-2/trace/brds": () => jsonResponse(200, [{ path: BRD, title: "X", trust_tier: "human_verified", status: "stable" }]),
      "GET /api/session": () => jsonResponse(200, { ...SIGNED_IN, signed_in: false }),
      "GET /api/workspaces/ws-2/trace": () => jsonResponse(200, trace(false)),
    });
    render(<TracePanel workspace={WORKSPACE} brd={BRD} onSelectBrd={() => {}} />);
    expect(await screen.findByText("AC-01 has no test evidence yet.")).toBeInTheDocument();
    expect(screen.getByText("0 errors · 2 warnings", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("merged")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm…" })).not.toBeInTheDocument();
  });

  it("lets a signed-in person confirm an inferred link", async () => {
    let confirmed = false;
    mockApi({
      "GET /api/workspaces/ws-2/trace/brds": () => jsonResponse(200, [{ path: BRD, title: "X", trust_tier: "human_verified", status: "stable" }]),
      "GET /api/session": () => jsonResponse(200, SIGNED_IN),
      "GET /api/workspaces/ws-2/trace": () => jsonResponse(200, trace(confirmed)),
      "POST /api/workspaces/ws-2/trace/confirmations": () => {
        confirmed = true;
        return jsonResponse(201, { link: "pull_request:20->file:tests/t.py", confirmed_by: "human:octo", note: null, created_at: "2026-09-20T12:00:00Z" });
      },
    });
    vi.spyOn(window, "prompt").mockReturnValue("Checked the diff.");
    render(<TracePanel workspace={WORKSPACE} brd={BRD} onSelectBrd={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm…" }));
    expect(await screen.findByText("inferred, confirmed")).toBeInTheDocument();
    expect(screen.queryByText("tests/t.py was linked by inference.")).not.toBeInTheDocument();
  });
});
