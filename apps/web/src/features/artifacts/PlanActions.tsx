import { useState } from "react";
import type { ArtifactDetail } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

/** Titles of the plan's Proposed decisions, in order (the API reads the same section). */
export function decisionTitles(content: string): string[] {
  const section = content.split("\n## Proposed decisions\n")[1];
  if (!section) return [];
  return (section.split("\n## ")[0] ?? "")
    .split("\n")
    .filter((line) => line.startsWith("### "))
    .map((line) => line.slice(4).trim());
}

type Props = {
  artifact: ArtifactDetail;
  onOpenApproval?: ((approvalId: string) => void) | undefined;
};

/** From a plan: propose the Story's draft pull request, or publish a proposed decision. */
export function PlanActions({ artifact, onOpenApproval }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { artifact_id: artifact.id };
  const titles = decisionTitles(artifact.current.content);

  async function propose(request: () => Promise<{ data?: { id: string }; error?: unknown }>) {
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await request();
      if (data) onOpenApproval?.(data.id);
      else setError(detailOf(failure) ?? "The action could not be proposed.");
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-label="Implementation">
      <h2>Implementation</h2>
      <p className="hint">
        A draft pull request starts a branch from one empty commit, linked to the Story, with this
        plan's summary and the context it used. Nothing is written until you approve, and no file
        changes until an engineer pushes code.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          void propose(() =>
            api.POST("/api/artifacts/{artifact_id}/draft-pull-request", { params: { path } }),
          )
        }
      >
        {busy ? "Preparing…" : "Open draft PR…"}
      </button>
      {titles.length > 0 && (
        <>
          <h3>Proposed decisions</h3>
          {titles.map((title, index) => (
            <p key={title}>
              <button
                type="button"
                className="button--secondary"
                disabled={busy}
                onClick={() =>
                  void propose(() =>
                    api.POST("/api/artifacts/{artifact_id}/decisions", {
                      params: { path },
                      body: { index: index + 1 },
                    }),
                  )
                }
              >
                Publish decision: {title}…
              </button>
            </p>
          ))}
        </>
      )}
      {error && (
        <p role="alert" className="text-bad">
          {error}
        </p>
      )}
    </section>
  );
}
