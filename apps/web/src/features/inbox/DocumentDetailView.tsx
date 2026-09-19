import { useEffect, useState } from "react";
import type { DocumentDetail, KnowledgeLink } from "@ichnos/api-client";

import { api } from "../../api";
import { LinkList } from "../../components/LinkList";
import { TrustTierBadge, trustTier } from "../../components/TrustTierBadge";
import { UNREACHABLE } from "../../labels";

type Props = {
  workspaceId: string;
  path: string;
  onOpenDocument: (path: string) => void;
  onBack: () => void;
};

export function DocumentDetailView({ workspaceId, path, onOpenDocument, onBack }: Props) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [links, setLinks] = useState<KnowledgeLink[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "failed">("loading");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    async function load() {
      try {
        const [detail, related] = await Promise.all([
          api.GET("/api/workspaces/{workspace_id}/documents/detail", {
            params: { path: { workspace_id: workspaceId }, query: { path } },
          }),
          api.GET("/api/workspaces/{workspace_id}/links", {
            params: { path: { workspace_id: workspaceId }, query: { kind: "document", key: path } },
          }),
        ]);
        if (cancelled) return;
        if (!detail.data) {
          setState("missing");
          return;
        }
        setDoc(detail.data);
        setLinks(related.data ?? []);
        setState("ready");
      } catch {
        if (!cancelled) setState("failed");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, path]);

  const back = (
    <button type="button" className="back" onClick={onBack}>
      ← All documents
    </button>
  );
  if (state === "loading") return <p className="hint">Loading document…</p>;
  if (state === "failed") return <>{back}<p className="notice notice--bad">{UNREACHABLE}</p></>;
  if (state === "missing" || !doc) {
    return (
      <>
        {back}
        <p className="notice notice--bad">
          {path} is not in the synced documents. It may have been removed; sync again to check.
        </p>
      </>
    );
  }

  const outgoing = links.filter((l) => l.source_kind === "document" && l.source_key === path);
  const incoming = links.filter((l) => l.target_kind === "document" && l.target_key === path);
  return (
    <article aria-labelledby="doc-title" className="detail">
      {back}
      <h1 id="doc-title">{doc.title ?? doc.path}</h1>
      <p className="path">{doc.path}</p>
      {doc.description && <p className="lede">{doc.description}</p>}
      <dl className="facts">
        <div>
          <dt>Type</dt>
          <dd>{doc.type ?? "—"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{doc.status ?? "—"}</dd>
        </div>
        <div>
          <dt>Trust</dt>
          <dd>
            <TrustTierBadge tier={doc.trust_tier} />
            <span className="facts__help">{trustTier(doc.trust_tier).help}</span>
          </dd>
        </div>
        <div>
          <dt>Synced from</dt>
          <dd className="path">{doc.commit_sha.slice(0, 7)}</dd>
        </div>
      </dl>

      <section className="panel" aria-label="Findings">
        <h2>Findings</h2>
        {doc.finding_details.length === 0 ? (
          <p className="hint">No conformance findings. This document follows OKF v0.2.</p>
        ) : (
          <ul className="findings">
            {doc.finding_details.map((finding, index) => (
              <li key={`${finding.code}:${index}`}>
                <span className={finding.level === "error" ? "text-bad" : "text-warn"}>
                  {finding.level}
                </span>{" "}
                <code>{finding.code}</code> {finding.message}
                {finding.line !== null && <span className="hint"> (line {finding.line})</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <LinkList
        title="Links from this document"
        links={outgoing}
        direction="outgoing"
        onOpenDocument={onOpenDocument}
      />
      <LinkList
        title="Links to this document"
        links={incoming}
        direction="incoming"
        onOpenDocument={onOpenDocument}
      />

      <section className="panel" aria-label="Content">
        <h2>Content</h2>
        <pre className="body">{doc.body}</pre>
      </section>
    </article>
  );
}
