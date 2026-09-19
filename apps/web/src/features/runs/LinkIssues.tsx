import { useState } from "react";
import type { RunDetail } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";
import { routeHash } from "../../route";

/** After the BRD's pull request is merged, propose writing the Issue numbers into it. */
export function LinkIssues({ run }: { run: RunDetail }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const result = (run.outputs.result ?? {}) as { issues?: unknown; follow_up_approval_id?: string | null };
  if (run.workflow_type !== "planning" || !result.issues || result.follow_up_approval_id) return null;

  async function link() {
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/runs/{run_id}/link-issues", {
        params: { path: { run_id: run.id } },
      });
      const id = (data?.outputs.result as { follow_up_approval_id?: string } | undefined)?.follow_up_approval_id;
      if (id) window.location.hash = routeHash({ section: "approvals", approval: id });
      else setError(detailOf(failure) ?? "Linking could not be proposed.");
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-label="Link Issues">
      <h2>Link Issues into the BRD</h2>
      <p className="hint">
        Once the BRD's pull request is merged, propose recording the Epic and Stories in its frontmatter.
      </p>
      <button type="button" onClick={() => void link()} disabled={busy}>
        {busy ? "Proposing…" : "Link Issues into the BRD"}
      </button>
      {error && (
        <p role="alert" className="text-bad">
          {error}
        </p>
      )}
    </section>
  );
}
