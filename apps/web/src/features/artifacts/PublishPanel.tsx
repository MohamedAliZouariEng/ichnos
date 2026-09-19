import { useState } from "react";
import type { ArtifactDetail } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

type Props = {
  artifact: ArtifactDetail;
  onOpenApproval?: ((approvalId: string) => void) | undefined;
  onOpenRun?: ((runId: string) => void) | undefined;
};

/** Publish a draft BRD, or plan an approved one; both wait for approval before writing. */
export function PublishPanel({ artifact, onOpenApproval, onOpenRun }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { artifact_id: artifact.id };

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/artifacts/{artifact_id}/publish", {
        params: { path },
      });
      if (data) onOpenApproval?.(data.id);
      else setError(detailOf(failure) ?? "Publishing could not start.");
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  async function plan() {
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/artifacts/{artifact_id}/plan", {
        params: { path },
      });
      if (data) onOpenRun?.(data.id);
      else setError(detailOf(failure) ?? "Planning could not start.");
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  if (artifact.kind !== "brd") return null;
  return (
    <section className="panel" aria-label="Publishing">
      <h2>Publishing</h2>
      {artifact.status === "draft" && (
        <>
          <p className="hint">
            Publishing proposes a pull request that writes this BRD as a human-verified OKF concept.
            Nothing is written until you approve it.
          </p>
          <button type="button" onClick={() => void publish()} disabled={busy}>
            {busy ? "Preparing…" : "Publish…"}
          </button>
        </>
      )}
      {artifact.status === "needs-review" && (
        <p className="notice notice--warn">A publish action is waiting in Approvals.</p>
      )}
      {artifact.status === "approved" && (
        <>
          <p className="hint">
            Approved. Plan one Epic and 3–5 Stories; creating them in GitHub waits for your approval.
          </p>
          <button type="button" onClick={() => void plan()} disabled={busy}>
            {busy ? "Starting…" : "Plan Epic and Stories"}
          </button>
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
