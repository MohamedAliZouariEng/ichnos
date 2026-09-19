import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { RunsPanel } from "./RunsPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const CONFIG = {
  github_token_configured: true, llm_provider: "openai-compatible", llm_model: "gemini-3.8-flash",
  llm_configured: true, llm_host: "generativelanguage.googleapis.com", llm_local: false,
  llm_reasoning_effort: "low", embedding_provider: null, embedding_model: null,
};
const NOTE = {
  path: "docs/meetings/2026-09-15-workspace-onboarding.md", kind: "concept", concept_id: "x",
  type: "Meeting Note", title: "Workspace onboarding sync", status: "stable",
  trust_tier: "human_verified", findings: 0, commit_sha: "abc1234",
};
const SOURCE = {
  id: "src-1", kind: "document", title: "Workspace onboarding sync", filename: null,
  document_path: NOTE.path, commit_sha: "abc1234", media_type: "text/markdown",
  content_sha256: "0".repeat(64), size: 10, created_by: "human:local",
  created_at: "2026-09-19T12:00:00Z", proposed_path: null, content: "…", reused: false,
};

function ev(id: number, kind: string, stage: string | null, message: string, data = {}) {
  return { id, kind, stage, message, data, created_at: "2026-09-19T12:00:00Z" };
}

function run(status: string, events: ReturnType<typeof ev>[], extra: object = {}) {
  return {
    id: "run-1", workspace_id: "ws-2", workflow_type: "requirements", status,
    stage: events[events.length - 1]?.stage ?? null, error: null,
    created_at: "2026-09-19T12:00:00Z", finished_at: null, total_tokens: 0, artifact_id: null,
    inputs: {}, outputs: {}, events, ...extra,
  };
}

const STARTED = [
  ev(1, "run.queued", null, "requirements run queued"),
  ev(2, "run.started", null, "Run started"),
  ev(3, "stage.started", "retrieval", "retrieval"),
  ev(4, "stage.completed", "retrieval", "7 context items", { duration_ms: 600 }),
  ev(5, "stage.started", "requirements", "requirements"),
];
const FINISHED = [
  ...STARTED,
  ev(6, "stage.completed", "requirements", "4 requirements, 1 assumptions, 4 open questions", {
    duration_ms: 3500,
  }),
  ev(7, "stage.started", "specification", "specification"),
  ev(8, "stage.completed", "specification", "BRD drafted", { duration_ms: 20 }),
  ev(9, "run.completed", null, "Run completed"),
];

function mockList(overrides: Record<string, () => Response> = {}) {
  mockApi({
    "GET /api/config": () => jsonResponse(200, CONFIG),
    "GET /api/workspaces/ws-2/documents": () => jsonResponse(200, [NOTE]),
    "GET /api/workspaces/ws-2/runs": () => jsonResponse(200, []),
    ...overrides,
  });
}

describe("RunsPanel", () => {
  it("drafts a BRD from a synced meeting note", async () => {
    mockList({
      "POST /api/workspaces/ws-2/sources/from-document": () => jsonResponse(201, SOURCE),
      "POST /api/workspaces/ws-2/runs": () => jsonResponse(202, run("queued", STARTED.slice(0, 1))),
    });
    const onOpenRun = vi.fn();
    render(<RunsPanel workspace={WORKSPACE} onOpenRun={onOpenRun} onCloseRun={() => {}} />);

    expect(await screen.findByRole("option", { name: /synced meeting note/ })).toBeInTheDocument();
    expect(screen.getByText(/are sent to generativelanguage.googleapis.com/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Draft BRD" }));
    await vi.waitFor(() => expect(onOpenRun).toHaveBeenCalledWith("run-1"));
  });

  it("drafts a BRD from pasted text", async () => {
    mockList({
      "POST /api/workspaces/ws-2/sources": () => jsonResponse(201, { ...SOURCE, kind: "pasted" }),
      "POST /api/workspaces/ws-2/runs": () => jsonResponse(202, run("queued", [])),
    });
    const onOpenRun = vi.fn();
    render(<RunsPanel workspace={WORKSPACE} onOpenRun={onOpenRun} onCloseRun={() => {}} />);

    await screen.findByRole("option", { name: /synced meeting note/ });
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "__paste__" } });
    const button = screen.getByRole("button", { name: "Draft BRD" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Meeting note text"), {
      target: { value: "Invitations must expire after 7 days." },
    });
    fireEvent.click(button);
    await vi.waitFor(() => expect(onOpenRun).toHaveBeenCalledWith("run-1"));
  });

  it("cannot start without a configured model", async () => {
    mockList({
      "GET /api/config": () => jsonResponse(200, { ...CONFIG, llm_configured: false }),
    });
    render(<RunsPanel workspace={WORKSPACE} onOpenRun={() => {}} onCloseRun={() => {}} />);
    expect(await screen.findByText(/No model is configured/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft BRD" })).toBeDisabled();
  });

  it("lists recent runs", async () => {
    mockList({
      "GET /api/workspaces/ws-2/runs": () =>
        jsonResponse(200, [{ ...run("succeeded", []), total_tokens: 2291, stage: "specification" }]),
    });
    render(<RunsPanel workspace={WORKSPACE} onOpenRun={() => {}} onCloseRun={() => {}} />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("succeeded")).toBeInTheDocument();
    expect(within(table).getByText("2291")).toBeInTheDocument();
  });
});

describe("RunDetailsView", () => {
  it("follows a run until it completes", async () => {
    let calls = 0;
    mockApi({
      "GET /api/runs/run-1": () => {
        calls += 1;
        if (calls === 1) return jsonResponse(200, run("running", STARTED));
        return jsonResponse(
          200,
          run("succeeded", FINISHED, {
            total_tokens: 2291,
            artifact_id: "art-1",
            outputs: { result: { path: "docs/specs/x/brd.md", version: 1, requirements: 4, findings: 0 } },
          }),
        );
      },
    });
    render(
      <RunsPanel workspace={WORKSPACE} runId="run-1" onOpenRun={() => {}} onCloseRun={() => {}} pollMs={200} />,
    );

    const stages = await screen.findByRole("list", { name: "Stages" });
    expect(within(stages).getByText("7 context items")).toBeInTheDocument();
    expect(within(stages).getByText("Running…")).toBeInTheDocument();

    expect(
      await within(stages).findByText("4 requirements, 1 assumptions, 4 open questions"),
    ).toBeInTheDocument();
    expect(await screen.findByText("docs/specs/x/brd.md")).toBeInTheDocument();
    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(within(stages).getAllByText(/^Done/)).toHaveLength(3);
  });

  it("shows why a run failed", async () => {
    mockApi({
      "GET /api/runs/run-1": () =>
        jsonResponse(200, {
          ...run("failed", [
            ...STARTED,
            ev(6, "stage.failed", "requirements", "The model provider returned HTTP 429"),
            ev(7, "run.failed", null, "requirements: The model provider returned HTTP 429"),
          ]),
          error: "requirements: The model provider returned HTTP 429",
        }),
    });
    render(<RunsPanel workspace={WORKSPACE} runId="run-1" onOpenRun={() => {}} onCloseRun={() => {}} />);
    expect(
      await screen.findByText("requirements: The model provider returned HTTP 429", {
        selector: "p.notice",
      }),
    ).toHaveClass("notice");
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
