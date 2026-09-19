import { useEffect, useRef, useState } from "react";
import type { ApprovalDetail, ApproverSession } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";
import { StatusBadge } from "../runs/StatusBadge";
import { IssuesEditor } from "./IssuesEditor";
import { ACTION_LABEL, type DocsPayload, type IssueSpec, type IssuesPayload } from "./payload";

function DocsView({ payload, base }: { payload: DocsPayload; base: Record<string, unknown> }) {
  const shas = (base.files ?? {}) as Record<string, string | null>;
  return (
    <>
      <section className="panel" aria-label="Pull request">
        <h2>{payload.title}</h2>
        <p className="path">
          {payload.branch} → {payload.base_branch}
        </p>
        <pre className="payload-text">{payload.body}</pre>
      </section>
      <section className="panel" aria-label="Files">
        <h2>Files ({payload.files.length})</h2>
        {payload.files.map((file) => (
          <details key={file.path} className="payload-file">
            <summary>
              <span className="path">{file.path}</span>{" "}
              <span className={`badge badge--${shas[file.path] ? "info" : "ok"}`}>
                {shas[file.path] ? "changes an existing file" : "new file"}
              </span>
            </summary>
            <pre className="payload-text">{file.content}</pre>
          </details>
        ))}
      </section>
    </>
  );
}

function IssueCard({ issue, heading }: { issue: IssueSpec; heading: string }) {
  return (
    <article className="issue-card">
      <h3>
        {heading}: {issue.title}
      </h3>
      <p>
        {issue.labels.map((label) => (
          <span key={label} className="chip">
            {label}
          </span>
        ))}
      </p>
      <pre className="payload-text">{issue.body}</pre>
    </article>
  );
}

function IssuesView({ payload }: { payload: IssuesPayload }) {
  return (
    <section className="panel" aria-label="Issues">
      <h2>1 Epic and {payload.stories.length} Stories</h2>
      <p className="hint">
        <code>#{"{epic}"}</code> and <code>#{"{S-1}"}</code> become the numbers GitHub assigns when
        the Issues are created; nothing else changes.
      </p>
      <IssueCard issue={payload.epic} heading="Epic" />
      {payload.stories.map((story) => (
        <IssueCard key={story.key ?? story.title} issue={story} heading={story.key ?? "Story"} />
      ))}
    </section>
  );
}

function Result({ approval }: { approval: ApprovalDetail }) {
  const result = (approval.result ?? {}) as Record<string, any>;
  if (approval.status === "executed" && result.pull_request) {
    return (
      <p className="notice notice--ok">
        Pull request opened:{" "}
        <a href={result.pull_request.url} target="_blank" rel="noopener noreferrer">
          #{result.pull_request.number}
        </a>
        . Review and merge it on GitHub.
      </p>
    );
  }
  if (result.epic) {
    const stories = (result.stories ?? []) as { key: string; number: number; url: string }[];
    return (
      <div className={`notice notice--${approval.status === "executed" ? "ok" : "bad"}`}>
        <p>
          Epic{" "}
          <a href={result.epic.url} target="_blank" rel="noopener noreferrer">
            #{result.epic.number}
          </a>
          {stories.length > 0 && " and Stories "}
          {stories.map((story, index) => (
            <span key={story.key}>
              {index > 0 && ", "}
              <a href={story.url} target="_blank" rel="noopener noreferrer">
                #{story.number}
              </a>
            </span>
          ))}{" "}
          were created.
        </p>
        {approval.error && <p>{approval.error}</p>}
      </div>
    );
  }
  if (approval.error) return <p className="notice notice--bad">{approval.error}</p>;
  if (approval.status === "rejected") {
    return <p className="notice">Rejected{approval.decision_note ? `: ${approval.decision_note}` : "."}</p>;
  }
  return null;
}

type Props = { approvalId: string; onBack: () => void };

export function ApprovalReview({ approvalId, onBack }: Props) {
  const [approval, setApproval] = useState<ApprovalDetail | null>(null);
  const [session, setSession] = useState<ApproverSession | null>(null);
  const [failed, setFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const path = { approval_id: approvalId };

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [detail, current] = await Promise.all([
          api.GET("/api/approvals/{approval_id}", { params: { path: { approval_id: approvalId } } }),
          api.GET("/api/session"),
        ]);
        if (cancelled) return;
        if (detail.data) setApproval(detail.data);
        else setFailed(true);
        setSession(current.data ?? null);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [approvalId]);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  async function decide(action: "approve" | "reject") {
    if (!approval) return;
    setBusy(true);
    setError(null);
    try {
      const response =
        action === "approve"
          ? await api.POST("/api/approvals/{approval_id}/approve", {
              params: { path },
              body: { payload_hash: approval.payload_hash },
            })
          : await api.POST("/api/approvals/{approval_id}/reject", {
              params: { path },
              body: { note: note.trim() || null },
            });
      if (response.data) {
        setApproval(response.data);
        setConfirming(false);
      } else {
        setError(detailOf(response.error) ?? "The decision could not be saved.");
      }
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <button type="button" className="back" onClick={onBack}>
      ← All approvals
    </button>
  );
  if (failed) {
    return (
      <>
        {back}
        <p className="notice notice--bad">{UNREACHABLE}</p>
      </>
    );
  }
  if (!approval) return <p className="hint">Loading approval…</p>;

  const payload = approval.payload as unknown as DocsPayload | IssuesPayload;
  const preparedFor = (approval.payload as { approver?: string }).approver;
  const mismatch = session?.signed_in && preparedFor && preparedFor !== session.approver;
  return (
    <article aria-labelledby="approval-title" className="detail">
      {back}
      <h1 id="approval-title">{approval.summary ?? ACTION_LABEL[approval.action_type]}</h1>
      <dl className="facts">
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={approval.status} />
          </dd>
        </div>
        <div>
          <dt>Writes to</dt>
          <dd className="path">
            {approval.target} ({approval.branch})
          </dd>
        </div>
        <div>
          <dt>Proposed by</dt>
          <dd className="path">{approval.proposed_by}</dd>
        </div>
        <div>
          <dt>Payload hash</dt>
          <dd>
            <code>{approval.payload_hash.slice(0, 12)}</code>{" "}
            <span className={`badge badge--${approval.hash_ok ? "ok" : "bad"}`}>
              {approval.hash_ok ? "hash verified" : "hash mismatch"}
            </span>
          </dd>
        </div>
      </dl>

      <Result approval={approval} />

      {approval.status === "pending" && (
        <section className="panel decision" aria-label="Decision">
          <h2>Decision</h2>
          {!session?.signed_in ? (
            <p className="notice notice--warn">Sign in to approve, using the control in the top bar.</p>
          ) : mismatch ? (
            <p className="notice notice--warn">
              This action was prepared for {preparedFor}; you are signed in as {session.approver}.
            </p>
          ) : confirming ? (
            <div
              className="actions"
              onKeyDown={(event) => {
                if (event.key === "Escape") setConfirming(false);
              }}
            >
              <p>
                This writes to <span className="path">{approval.target}</span> exactly as shown below.
              </p>
              <button ref={confirmRef} type="button" onClick={() => void decide("approve")} disabled={busy}>
                {busy ? "Writing to GitHub…" : "Confirm and write to GitHub"}
              </button>
              <button type="button" className="button--secondary" onClick={() => setConfirming(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <>
              <div className="actions">
                <button type="button" onClick={() => setConfirming(true)}>
                  Approve…
                </button>
                {payload.kind === "create_issues" && !editing && (
                  <button type="button" className="button--secondary" onClick={() => setEditing(true)}>
                    Edit Issues…
                  </button>
                )}
              </div>
              <label htmlFor="reject-note">Reject with a note (optional)</label>
              <textarea
                id="reject-note"
                rows={2}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <div className="actions">
                <button
                  type="button"
                  className="button--secondary"
                  onClick={() => void decide("reject")}
                  disabled={busy}
                >
                  Reject
                </button>
              </div>
            </>
          )}
          {error && (
            <p role="alert" className="text-bad">
              {error}
            </p>
          )}
        </section>
      )}

      {editing && payload.kind === "create_issues" ? (
        <IssuesEditor
          approval={approval}
          payload={payload}
          onSaved={(saved) => {
            setApproval(saved);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : payload.kind === "docs_pull_request" ? (
        <DocsView payload={payload} base={approval.base} />
      ) : (
        <IssuesView payload={payload} />
      )}
    </article>
  );
}
