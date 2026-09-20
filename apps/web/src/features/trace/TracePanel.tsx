import { useCallback, useEffect, useState } from "react";
import type { ApproverSession, BrdRead, TraceRead, TraceRowRead, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

type Finding = TraceRead["findings"][number];

const GOOD = ["approved", "merged", "passing", "success", "tested: passing", "committed", "done"];
const BAD = ["missing", "failing", "failure", "tested: failing", "closed without merging"];

function tone(status: string): string {
  if (GOOD.includes(status)) return "ok";
  if (BAD.includes(status)) return "bad";
  return "warn";
}

type RowProps = {
  row: TraceRowRead;
  depth: number;
  findings: Map<string, Finding[]>;
  canConfirm: boolean;
  onConfirm: (link: string) => void;
};

function TraceRowView({ row, depth, findings, canConfirm, onConfirm }: RowProps) {
  return (
    <li id={`row-${row.id}`} className="trace-row" style={{ marginLeft: `${depth * 1.25}rem` }}>
      <p>
        <code>{row.id}</code> <span className="trace-level">{row.level.replace("_", " ")}</span>{" "}
        <strong>{row.key}</strong>{" "}
        {row.url ? (
          <a href={row.url} target="_blank" rel="noopener noreferrer">
            {row.title}
          </a>
        ) : (
          row.title
        )}{" "}
        <span className={`badge badge--${tone(row.status)}`}>{row.status}</span>
      </p>
      <ul className="trace-evidence">
        {row.evidence.map((e) => (
          <li key={`${e.source}-${e.text}`} className="hint">
            {e.text} ·{" "}
            {e.url ? (
              <a href={e.url} target="_blank" rel="noopener noreferrer">
                {e.source}
              </a>
            ) : (
              e.source
            )}
            {e.origin === "inferred" && (
              <>
                {" "}
                <span className={`badge badge--${e.confirmed ? "ok" : "warn"}`}>
                  {e.confirmed ? "inferred, confirmed" : "inferred"}
                </span>
                {!e.confirmed && canConfirm && e.link && (
                  <button type="button" className="link" onClick={() => onConfirm(e.link ?? "")}>
                    Confirm…
                  </button>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {(findings.get(row.id) ?? []).map((f) => (
        <p key={f.code} className={`notice notice--${f.level === "error" ? "bad" : "warn"}`}>
          {f.message}
        </p>
      ))}
      {row.children.length > 0 && (
        <ul className="trace-children">
          {row.children.map((child) => (
            <TraceRowView
              key={child.id}
              row={child}
              depth={depth + 1}
              findings={findings}
              canConfirm={canConfirm}
              onConfirm={onConfirm}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

type Props = {
  workspace: Workspace;
  brd?: string | undefined;
  onSelectBrd: (path: string) => void;
};

/** Requirement → Epic → Story → criterion → pull request → commit → test (ADR-0022). */
export function TracePanel({ workspace, brd, onSelectBrd }: Props) {
  const [brds, setBrds] = useState<BrdRead[] | null>(null);
  const [trace, setTrace] = useState<TraceRead | null>(null);
  const [session, setSession] = useState<ApproverSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [list, current] = await Promise.all([
          api.GET("/api/workspaces/{workspace_id}/trace/brds", {
            params: { path: { workspace_id: workspace.id } },
          }),
          api.GET("/api/session"),
        ]);
        setBrds(list.data ?? []);
        setSession(current.data ?? null);
        const first = list.data?.[0];
        if (!brd && first) onSelectBrd(first.path);
      } catch {
        setError(UNREACHABLE);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.id]);

  const load = useCallback(async () => {
    if (!brd) return;
    try {
      const { data, error: failure } = await api.GET("/api/workspaces/{workspace_id}/trace", {
        params: { path: { workspace_id: workspace.id }, query: { brd } },
      });
      if (data) setTrace(data);
      else setError(detailOf(failure) ?? "The trace could not be built.");
    } catch {
      setError(UNREACHABLE);
    }
  }, [workspace.id, brd]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirm(link: string) {
    if (!brd) return;
    const note = window.prompt("Why is this link right? (optional)") ?? undefined;
    const { error: failure } = await api.POST("/api/workspaces/{workspace_id}/trace/confirmations", {
      params: { path: { workspace_id: workspace.id } },
      body: { brd, link, note: note || null },
    });
    if (failure) setError(detailOf(failure) ?? "The link could not be confirmed.");
    await load();
  }

  const findings = new Map<string, Finding[]>();
  for (const f of trace?.findings ?? []) findings.set(f.row, [...(findings.get(f.row) ?? []), f]);
  const errors = trace?.findings.filter((f) => f.level === "error").length ?? 0;
  const warnings = (trace?.findings.length ?? 0) - errors;

  return (
    <section aria-labelledby="trace-title">
      <h1 id="trace-title">Traceability</h1>
      <p className="lede">
        Each requirement of a BRD, followed to Stories, pull requests, commits and tests. Every row
        shows its status and the evidence behind it.
      </p>
      {brds && brds.length === 0 && <p className="empty">No BRD has been synced yet.</p>}
      {brds && brds.length > 0 && (
        <p>
          <label htmlFor="trace-brd">BRD </label>
          <select id="trace-brd" value={brd ?? ""} onChange={(e) => onSelectBrd(e.target.value)}>
            {brds.map((b) => (
              <option key={b.path} value={b.path}>
                {b.title ?? b.path}
              </option>
            ))}
          </select>
        </p>
      )}
      {error && (
        <p role="alert" className="notice notice--bad">
          {error}
        </p>
      )}
      {trace && (
        <>
          <p className="hint">
            Trace <code>{trace.hash.slice(0, 12)}</code> · {errors} errors · {warnings} warnings
          </p>
          <ul className="trace-tree" aria-label="Trace">
            {trace.rows.map((row) => (
              <TraceRowView
                key={row.id}
                row={row}
                depth={0}
                findings={findings}
                canConfirm={Boolean(session?.signed_in)}
                onConfirm={(link) => void confirm(link)}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
