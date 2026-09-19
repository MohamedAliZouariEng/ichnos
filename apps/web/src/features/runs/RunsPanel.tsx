import { useEffect, useState } from "react";
import type { RunSummary, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE } from "../../labels";
import { NewRunForm } from "./NewRunForm";
import { RunDetailsView } from "./RunDetailsView";
import { StatusBadge } from "./StatusBadge";

type Props = {
  workspace: Workspace;
  runId?: string | undefined;
  onOpenRun: (runId: string) => void;
  onCloseRun: () => void;
  pollMs?: number | undefined;
};

export function RunsPanel({ workspace, runId, onOpenRun, onCloseRun, pollMs }: Props) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (runId) return;
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/runs", {
          params: { path: { workspace_id: workspace.id } },
        });
        if (!cancelled) setRuns(data ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspace.id, runId]);

  if (runId) return <RunDetailsView runId={runId} onBack={onCloseRun} pollMs={pollMs} />;

  return (
    <section aria-labelledby="runs-title">
      <h1 id="runs-title">Workflow runs</h1>
      <p className="lede">Draft a BRD from a meeting note in {workspace.repository}.</p>
      <NewRunForm workspace={workspace} onStarted={onOpenRun} />

      <h2>Recent runs</h2>
      {failed && <p className="notice notice--bad">{UNREACHABLE}</p>}
      {!failed && runs === null && <p className="hint">Loading runs…</p>}
      {runs?.length === 0 && <p className="empty">No runs yet. Draft a BRD above to start one.</p>}
      {runs && runs.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">Workflow</th>
                <th scope="col">Status</th>
                <th scope="col">Stage</th>
                <th scope="col">Tokens</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <button type="button" className="link" onClick={() => onOpenRun(run.id)}>
                      {new Date(run.created_at).toLocaleString()}
                    </button>
                  </td>
                  <td>{run.workflow_type}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{run.stage ?? "—"}</td>
                  <td>{run.total_tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
