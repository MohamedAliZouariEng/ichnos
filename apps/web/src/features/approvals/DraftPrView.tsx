import type { DraftPrPayload } from "./payload";

/** A Story's draft pull request: an empty commit, a body that claims nothing (ADR-0021). */
export function DraftPrView({ payload }: { payload: DraftPrPayload }) {
  return (
    <section className="panel" aria-label="Draft pull request">
      <h2>
        {payload.title} <span className="badge badge--info">draft</span>
      </h2>
      <p className="path">
        {payload.branch} → {payload.base_branch}
      </p>
      <p className="notice notice--ok">
        One empty commit, “{payload.commit_message}”: 0 files change. Ichnos never marks it ready
        or merges it.
      </p>
      <p className="hint">
        Plan <code>{payload.plan.path}</code>, version {payload.plan.version}, SHA-256{" "}
        <code>{payload.plan.sha256.slice(0, 12)}</code> · context pack{" "}
        <code>{payload.pack_hash.slice(0, 12)}</code>
      </p>
      <pre className="payload-text">{payload.body}</pre>
    </section>
  );
}
