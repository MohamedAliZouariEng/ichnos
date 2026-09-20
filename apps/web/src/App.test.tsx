import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { jsonResponse, mockApi } from "./test/http";

const WORKSPACES = [
  { id: "ws-1", name: "ichnos", repository: "MohamedAliZouariEng/ichnos", branch: "main",
    index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
    embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z" },
  { id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
    index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
    embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z" },
];

function mockShell() {
  mockApi({
    "GET /healthz": () => jsonResponse(200, { status: "ok", version: "0.1.0", database: "ok", search: "ok" }),
    "GET /api/workspaces": () => jsonResponse(200, WORKSPACES),
    "GET /api/config": () => jsonResponse(200, {
      github_token_configured: true, llm_provider: null, llm_model: null,
      embedding_provider: null, embedding_model: null,
    }),
  });
}

afterEach(() => {
  window.location.hash = "";
  window.localStorage.clear();
});

describe("App", () => {
  it("navigates to the Inbox and keeps the section in the URL", async () => {
    mockShell();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Inbox" }));
    expect(await screen.findByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/inbox");
  });

  it("switches workspaces and remembers the choice", async () => {
    mockShell();
    window.location.hash = "#/github";
    render(<App />);
    const select = await screen.findByLabelText("Workspace");
    fireEvent.change(select, { target: { value: "ws-2" } });
    expect(
      await screen.findByText("Issues and pull requests synced from MohamedAliZouariEng/quire-demo."),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("ichnos.workspace")).toBe("ws-2");
  });

  it("shows later phases as unavailable", async () => {
    mockShell();
    render(<App />);
    expect(await screen.findByText("Traceability")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Traceability" })).toBeInTheDocument();
  });
});

describe("Quick tips", () => {
  it("opens by itself the first time, and from the button afterwards", async () => {
    window.localStorage.clear();
    render(<App />);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    cleanup();

    render(<App />);  // a second visit: no tips
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Quick tips" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
