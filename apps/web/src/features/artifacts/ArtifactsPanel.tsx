import { useEffect, useState } from "react";
import type { ArtifactSummary, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE } from "../../labels";
import { StatusBadge } from "../runs/StatusBadge";
import { ArtifactReview } from "./ArtifactReview";

type Props = {
  workspace: Workspace;
  artifactId?: string | undefined;
  onOpenArtifact: (artifactId: string) => void;
  onCloseArtifact: () => void;
  validateDelayMs?: number | undefined;
};

export function ArtifactsPanel({
  workspace,
  artifactId,
  onOpenArtifact,
  onCloseArtifact,
  validateDelayMs,
}: Props) {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (artifactId) return;
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/artifacts", {
          params: { path: { workspace_id: workspace.id } },
        });
        if (!cancelled) setArtifacts(data ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspace.id, artifactId]);

  if (artifactId) {
    return (
      <ArtifactReview
        artifactId={artifactId}
        onBack={onCloseArtifact}
        validateDelayMs={validateDelayMs}
      />
    );
  }
  return (
    <section aria-labelledby="artifacts-title">
      <h1 id="artifacts-title">Artifacts</h1>
      <p className="lede">
        Drafts waiting for review. Nothing here reaches {workspace.repository} until it is approved.
      </p>
      {failed && <p className="notice notice--bad">{UNREACHABLE}</p>}
      {!failed && artifacts === null && <p className="hint">Loading artifacts…</p>}
      {artifacts?.length === 0 && (
        <p className="empty">
          No drafts yet. Open <strong>Workflow runs</strong> and select <strong>Draft BRD</strong>.
        </p>
      )}
      {artifacts && artifacts.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Artifact</th>
                <th scope="col">Status</th>
                <th scope="col">Version</th>
                <th scope="col">Findings</th>
                <th scope="col">Changed</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((artifact) => (
                <tr key={artifact.id}>
                  <td>
                    <button
                      type="button"
                      className="link"
                      onClick={() => onOpenArtifact(artifact.id)}
                    >
                      {artifact.title}
                    </button>
                    <div className="path">{artifact.path}</div>
                  </td>
                  <td>
                    <StatusBadge status={artifact.status} />
                  </td>
                  <td>v{artifact.current_version}</td>
                  <td className={artifact.findings > 0 ? "text-warn" : undefined}>
                    {artifact.findings}
                  </td>
                  <td>{new Date(artifact.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
