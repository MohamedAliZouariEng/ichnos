import { useEffect, useState } from "react";
import type { DocumentSummary } from "@ichnos/api-client";

import { api } from "../../api";
import { TrustTierBadge } from "../../components/TrustTierBadge";
import { UNREACHABLE } from "../../labels";

type Props = { workspaceId: string; refreshKey: number; onOpen: (path: string) => void };

export function DocumentList({ workspaceId, refreshKey, onOpen }: Props) {
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/documents", {
          params: { path: { workspace_id: workspaceId } },
        });
        if (!cancelled) {
          setDocuments(data ?? []);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshKey]);

  if (failed) return <p className="notice notice--bad">{UNREACHABLE}</p>;
  if (documents === null) return <p className="hint">Loading documents…</p>;
  if (documents.length === 0) {
    return (
      <p className="empty">
        Nothing synced yet. Select <strong>Sync now</strong> to read this repository’s documents.
      </p>
    );
  }

  const concepts = documents.filter((doc) => doc.kind === "concept");
  const visible = showAll ? documents : concepts;
  return (
    <section aria-labelledby="documents-title" className="documents">
      <div className="documents__head">
        <h2 id="documents-title">Documents</h2>
        <label className="toggle">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(event) => setShowAll(event.target.checked)}
          />
          Show index, log and other files ({documents.length - concepts.length})
        </label>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Type</th>
              <th scope="col">Status</th>
              <th scope="col">Trust</th>
              <th scope="col">Findings</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((doc) => (
              <tr key={doc.path}>
                <td>
                  <button type="button" className="link" onClick={() => onOpen(doc.path)}>
                    {doc.title ?? doc.path}
                  </button>
                  <div className="path">{doc.path}</div>
                </td>
                <td>{doc.type ?? "—"}</td>
                <td>{doc.status ?? "—"}</td>
                <td>
                  <TrustTierBadge tier={doc.trust_tier} />
                </td>
                <td className={doc.findings > 0 ? "text-warn" : undefined}>{doc.findings}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
