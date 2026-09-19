import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { WorkspacePanel } from "./WorkspacePanel";

const WORKSPACE = {
  id: "ws-1",
  name: "ichnos",
  repository: "MohamedAliZouariEng/ichnos",
  branch: "main",
  index_paths: ["docs/", ".github/"],
  llm_provider: null,
  llm_model: null,
  embedding_provider: null,
  embedding_model: null,
  created_at: "2026-09-19T12:00:00Z",
  updated_at: "2026-09-19T12:00:00Z",
};

function config(tokenConfigured: boolean) {
  return {
    github_token_configured: tokenConfigured,
    llm_provider: null,
    llm_model: null,
    embedding_provider: null,
    embedding_model: null,
  };
}

describe("WorkspacePanel", () => {
  it("creates a workspace from the empty form", async () => {
    let posted: unknown;
    mockApi({
      "GET /api/workspaces": () => jsonResponse(200, []),
      "GET /api/config": () => jsonResponse(200, config(false)),
      "POST /api/workspaces": async (request) => {
        posted = await request.json();
        return jsonResponse(201, WORKSPACE);
      },
    });
    render(<WorkspacePanel />);

    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "ichnos" } });
    fireEvent.change(screen.getByLabelText("Repository"), {
      target: { value: "MohamedAliZouariEng/ichnos" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save workspace" }));

    expect(await screen.findByText("Workspace saved.")).toBeInTheDocument();
    expect(posted).toEqual({
      name: "ichnos",
      repository: "MohamedAliZouariEng/ichnos",
      branch: "main",
      index_paths: ["docs/", ".github/"],
      llm_provider: null,
      llm_model: null,
      embedding_provider: null,
      embedding_model: null,
    });
  });

  it("marks invalid fields with a plain-language hint", async () => {
    mockApi({
      "GET /api/workspaces": () => jsonResponse(200, [WORKSPACE]),
      "GET /api/config": () => jsonResponse(200, config(true)),
      "PATCH /api/workspaces/ws-1": () =>
        jsonResponse(422, {
          detail: [{ loc: ["body", "repository"], msg: "pattern mismatch", type: "string" }],
        }),
    });
    render(<WorkspacePanel />);

    fireEvent.change(await screen.findByLabelText("Repository"), {
      target: { value: "not a repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save workspace" }));

    expect(
      await screen.findByText("Use the form owner/name, for example octo-org/demo."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Repository")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows the API's explanation for a conflict", async () => {
    mockApi({
      "GET /api/workspaces": () => jsonResponse(200, []),
      "GET /api/config": () => jsonResponse(200, config(false)),
      "POST /api/workspaces": () =>
        jsonResponse(409, { detail: "A workspace with this name already exists." }),
    });
    render(<WorkspacePanel />);

    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "ichnos" } });
    fireEvent.change(screen.getByLabelText("Repository"), { target: { value: "octo-org/demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Save workspace" }));

    expect(
      await screen.findByText("A workspace with this name already exists."),
    ).toBeInTheDocument();
  });

  it("checks GitHub access for a saved workspace", async () => {
    mockApi({
      "GET /api/workspaces": () => jsonResponse(200, [WORKSPACE]),
      "GET /api/config": () => jsonResponse(200, config(true)),
      "POST /api/workspaces/ws-1/github-check": () =>
        jsonResponse(200, {
          token_configured: true,
          repository_accessible: true,
          branch_exists: true,
          default_branch: "main",
          private: false,
          message: "Repository and branch are accessible.",
        }),
    });
    render(<WorkspacePanel />);

    expect(await screen.findByText("configured")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check GitHub access" }));

    expect(
      await screen.findByText("Repository and branch are accessible. Default branch: main."),
    ).toBeInTheDocument();
  });

  it("explains how to add a missing token and disables the check before saving", async () => {
    mockApi({
      "GET /api/workspaces": () => jsonResponse(200, []),
      "GET /api/config": () => jsonResponse(200, config(false)),
    });
    render(<WorkspacePanel />);

    expect(await screen.findByText("not configured")).toBeInTheDocument();
    expect(screen.getByText(/Add ICHNOS_GITHUB_TOKEN to .env/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check GitHub access" })).toBeDisabled();
  });

  it("says so when the API cannot be reached", async () => {
    mockApi({});
    render(<WorkspacePanel />);

    expect(await screen.findByText(/Could not reach the API/)).toBeInTheDocument();
  });
});
