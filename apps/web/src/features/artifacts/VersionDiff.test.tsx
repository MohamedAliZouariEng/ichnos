import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi } from "../../test/http";
import { ArtifactsPanel } from "./ArtifactsPanel";
import { compare } from "./VersionDiff";

const FILLER = Array.from({ length: 20 }, (_, n) => `Line ${n + 1}`);
const GENERATED = [
  "---", "type: BRD", "---", "", ...FILLER,
  "**Should.** The product must provide a way to request a new invitation.[^s1]", "", "End.", "",
].join("\n");
const EDITED = GENERATED.replace("The product must provide", "The product should provide");
const V1 = {
  number: 1, origin: "generated", actor: "ichnos/gemini-3.8-flash", parent_number: null,
  note: null, created_at: "2026-09-19T12:00:00Z", findings: 0,
};
const V2 = { ...V1, number: 2, origin: "edited", actor: "human:local", parent_number: 1, note: "R-04" };

describe("compare", () => {
  it("counts changes and collapses long unchanged stretches", () => {
    const { rows, added, removed } = compare(GENERATED, EDITED);
    expect([added, removed]).toEqual([1, 1]);
    expect(rows.filter((row) => row.kind === "gap")).toEqual([{ kind: "gap", count: 18 }]);
    expect(rows.find((row) => row.kind === "del")).toMatchObject({
      text: "**Should.** The product must provide a way to request a new invitation.[^s1]",
    });
  });

  it("reports identical versions", () => {
    expect(compare("same\n", "same\n")).toMatchObject({ added: 0, removed: 0 });
  });
});

describe("Changes tab", () => {
  it("compares the generated version with the current one", async () => {
    mockApi({
      "GET /api/artifacts/art-1": () =>
        jsonResponse(200, {
          id: "art-1", workspace_id: "ws-2", kind: "brd", title: "Invitation expiry",
          slug: "invitation-expiry", path: "docs/specs/invitation-expiry/brd.md", status: "draft",
          current_version: 2, run_id: "run-1", created_at: "2026-09-19T12:00:00Z",
          updated_at: "2026-09-19T12:00:00Z", findings: 0, source_ids: ["src-1"],
          versions: [V1, V2], current: { ...V2, content: EDITED, finding_details: [] },
        }),
      "GET /api/artifacts/art-1/versions/1": () =>
        jsonResponse(200, { ...V1, content: GENERATED, finding_details: [] }),
    });
    const workspace = {
      id: "ws-2", name: "quire", repository: "o/quire", branch: "main", index_paths: ["docs/"],
      llm_provider: null, llm_model: null, embedding_provider: null, embedding_model: null,
      created_at: "2026-09-19T12:00:00Z", updated_at: "2026-09-19T12:00:00Z",
    };
    render(
      <ArtifactsPanel workspace={workspace} artifactId="art-1" onOpenArtifact={() => {}} onCloseArtifact={() => {}} />,
    );

    fireEvent.click(await screen.findByRole("tab", { name: "Changes" }));
    expect(await screen.findByText("1 line added, 1 line removed")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Changes from v1 to v2" })).toBeInTheDocument();
    expect(
      screen.getByText(/The product must provide/, { selector: ".diff__line--del .diff__text" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The product should provide/, { selector: ".diff__line--add .diff__text" }),
    ).toBeInTheDocument();
    expect(screen.getByText("⋯ 18 unchanged lines")).toBeInTheDocument();
  });
});
