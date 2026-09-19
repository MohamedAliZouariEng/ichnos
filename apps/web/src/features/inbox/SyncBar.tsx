import { useEffect, useState } from "react";
import type { SyncRun } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

function describe(run: SyncRun | null): string {
  if (!run) return "Not synced yet.";
  const when = new Date(run.finished_at ?? run.created_at).toLocaleString();
  if (run.status === "failed") return `Last sync failed (${when}): ${run.error ?? "unknown error"}`;
  if (run.status === "running") return `A sync started at ${when} is still running.`;
  const changes = Object.entries(run.counts)
    .filter(([key]) => /_(added|updated|deleted)$/.test(key))
    .reduce((total, [, value]) => total + value, 0);
  const noun = changes === 1 ? "change" : "changes";
  return `Last synced ${when}: ${changes} ${noun}, ${run.requests ?? 0} GitHub requests.`;
}

type Props = { workspaceId: string; onSynced: () => void };

export function SyncBar({ workspaceId, onSynced }: Props) {
  const [last, setLast] = useState<SyncRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/sync-runs", {
          params: { path: { workspace_id: workspaceId }, query: { limit: 1 } },
        });
        if (!cancelled) setLast(data?.[0] ?? null);
      } catch {
        // The document list reports an unreachable API; no need to say it twice.
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  async function sync() {
    setRunning(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/workspaces/{workspace_id}/sync", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (data) {
        setLast(data);
        onSynced();
      } else {
        setError(detailOf(failure) ?? "The sync could not start.");
      }
    } catch {
      setError(UNREACHABLE);
    } finally {
      setRunning(false);
    }
  }

  const failed = error !== null || last?.status === "failed";
  return (
    <div className="syncbar">
      <button type="button" onClick={() => void sync()} disabled={running}>
        {running ? "Syncing…" : "Sync now"}
      </button>
      <p className={failed ? "syncbar__status text-bad" : "syncbar__status"} role="status">
        {error ?? describe(last)}
      </p>
    </div>
  );
}
