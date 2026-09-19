import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { ArtifactsPanel } from "./ArtifactsPanel";

const WORKSPACE = {
  id: "ws-2", name: "quire", repository: "MohamedAliZouariEng/quire-demo", branch: "main",
  index_paths: ["docs/"], llm_provider: null, llm_model: null, embedding_provider: null,
  embedding_model: null, created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
};
const CONTENT = [
  "---", "type: BRD", "title: Invitation expiry", "status: draft", "---", "",
  "# Summary", "", "Links never expire.", "", "# Requirements", "", "## R-01", "",
  "**Must.** Invitations expire after 7 days.[^s1][^c1]", "",
  "[^s1]: [Workspace onboarding sync](/meetings/2026-09-19-onboarding.md)",
  "[^c1]: [Issue #1: Invitation lifecycle](https://github.com/o/r/issues/1)", "",
].join("\n");
const V1 = {
  number: 1, origin: "generated", actor: "ichnos/gemini-3.8-flash", parent_number: null,
  note: null, created_at: "2026-09-19T12:00:00Z", findings: 0,
};
const V2 = { ...V1, number: 2, origin: "edited", actor: "human:local", parent_number: 1, note: "Fixed R-01" };
const SUMMARY = {
  id: "art-1", workspace_id: "ws-2", kind: "brd", title: "Invitation expiry",
  slug: "invitation-expiry", path: "docs/specs/invitation-expiry/brd.md", status: "draft",
  current_version: 1, run_id: "run-1", created_at: "2026-09-19T12:00:00Z",
  updated_at: "2026-09-19T12:00:00Z", findings: 0,
};
const DETAIL = {
  ...SUMMARY, source_ids: ["src-1"], versions: [V1],
  current: { ...V1, content: CONTENT, finding_details: [] },
};
const noop = () => {};

function review(extra: Record<string, () => Response> = {}) {
  mockApi({ "GET /api/artifacts/art-1": () => jsonResponse(200, DETAIL), ...extra });
  render(
    <ArtifactsPanel
      workspace={WORKSPACE}
      artifactId="art-1"
      onOpenArtifact={noop}
      onCloseArtifact={noop}
      validateDelayMs={0}
    />,
  );
}

describe("ArtifactsPanel", () => {
  it("lists drafts and opens one", async () => {
    mockApi({ "GET /api/workspaces/ws-2/artifacts": () => jsonResponse(200, [SUMMARY]) });
    const onOpen = vi.fn();
    render(
      <ArtifactsPanel workspace={WORKSPACE} onOpenArtifact={onOpen} onCloseArtifact={noop} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Invitation expiry" }));
    expect(onOpen).toHaveBeenCalledWith("art-1");
    expect(screen.getByText("docs/specs/invitation-expiry/brd.md")).toBeInTheDocument();
  });

  it("renders the draft and lists its citations", async () => {
    review();
    expect(await screen.findByRole("heading", { name: "Requirements" })).toBeInTheDocument();
    const cited = screen.getByRole("region", { name: "Citations" });
    expect(within(cited).getByText("S1")).toBeInTheDocument();
    expect(within(cited).getByText("/meetings/2026-09-19-onboarding.md")).toBeInTheDocument();
    expect(within(cited).getByRole("link", { name: "Issue #1: Invitation lifecycle" })).toHaveAttribute(
      "href",
      "https://github.com/o/r/issues/1",
    );
  });

  it("saves an edit as the next version after checking it live", async () => {
    const saved = {
      ...DETAIL, current_version: 2, versions: [V1, V2],
      current: { ...V2, content: `${CONTENT}\nReviewed.\n`, finding_details: [] },
    };
    review({
      "POST /api/artifacts/art-1/validate": () => jsonResponse(200, []),
      "POST /api/artifacts/art-1/versions": () => jsonResponse(201, saved),
    });
    fireEvent.click(await screen.findByRole("tab", { name: "Edit" }));
    const save = screen.getByRole("button", { name: "Save as version 2" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Markdown"), { target: { value: `${CONTENT}\nReviewed.\n` } });
    const live = screen.getByRole("region", { name: "Live findings" });
    expect(await within(live).findByText("No OKF findings.")).toBeInTheDocument();
    fireEvent.click(save);
    expect(await screen.findByText("Saved version 2.")).toBeInTheDocument();
  });

  it("explains a stale save", async () => {
    review({
      "POST /api/artifacts/art-1/validate": () => jsonResponse(200, []),
      "POST /api/artifacts/art-1/versions": () =>
        jsonResponse(409, {
          detail: "Version 2 was saved after you started editing version 1; reload to see it before saving.",
        }),
    });
    fireEvent.click(await screen.findByRole("tab", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Markdown"), { target: { value: `${CONTENT}x` } });
    fireEvent.click(screen.getByRole("button", { name: "Save as version 2" }));
    expect(await screen.findByText(/Version 2 was saved after you started editing/)).toBeInTheDocument();
  });

  it("lists versions and opens an earlier one read-only", async () => {
    mockApi({
      "GET /api/artifacts/art-1": () =>
        jsonResponse(200, { ...DETAIL, current_version: 2, versions: [V1, V2], current: { ...V2, content: CONTENT, finding_details: [] } }),
      "GET /api/artifacts/art-1/versions/1": () =>
        jsonResponse(200, { ...V1, content: "---\ntype: BRD\n---\n\n# First draft\n", finding_details: [] }),
    });
    render(<ArtifactsPanel workspace={WORKSPACE} artifactId="art-1" onOpenArtifact={noop} onCloseArtifact={noop} />);

    fireEvent.click(await screen.findByRole("tab", { name: "Versions" }));
    const table = screen.getByRole("table");
    expect(within(table).getByText("generated")).toBeInTheDocument();
    expect(within(table).getByText("Fixed R-01")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "View version 1" }));
    expect(await screen.findByRole("heading", { name: "First draft" })).toBeInTheDocument();
    expect(screen.getByText(/Viewing version 1/)).toBeInTheDocument();
  });
});
