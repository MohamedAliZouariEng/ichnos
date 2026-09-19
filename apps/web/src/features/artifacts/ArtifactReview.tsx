import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ArtifactDetail, ArtifactVersion, Finding } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";
import { StatusBadge } from "../runs/StatusBadge";
import { citations, splitFrontmatter } from "./markdown";

type Tab = "preview" | "edit" | "versions";
const TABS: { id: Tab; label: string }[] = [
  { id: "preview", label: "Preview" },
  { id: "edit", label: "Edit" },
  { id: "versions", label: "Versions" },
];

function Findings({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return <p className="hint">No OKF findings.</p>;
  return (
    <ul className="findings">
      {findings.map((finding, index) => (
        <li key={`${finding.code}:${index}`}>
          <span className={finding.level === "error" ? "text-bad" : "text-warn"}>{finding.level}</span>{" "}
          <code>{finding.code}</code> {finding.message}
          {finding.line !== null && <span className="hint"> (line {finding.line})</span>}
        </li>
      ))}
    </ul>
  );
}

/** Rendered Markdown; no HTML from the document is executed. */
export function Preview({ content }: { content: string }) {
  const { frontmatter, body } = splitFrontmatter(content);
  return (
    <div className="preview">
      {frontmatter !== null && (
        <details className="frontmatter">
          <summary>Frontmatter</summary>
          <pre>{frontmatter}</pre>
        </details>
      )}
      <div className="markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
      </div>
    </div>
  );
}

type Props = { artifactId: string; onBack: () => void; validateDelayMs?: number | undefined };

export function ArtifactReview({ artifactId, onBack, validateDelayMs = 600 }: Props) {
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<Tab>("preview");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [live, setLive] = useState<Finding[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [viewing, setViewing] = useState<ArtifactVersion | null>(null);
  const params = { path: { artifact_id: artifactId } };

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/artifacts/{artifact_id}", {
          params: { path: { artifact_id: artifactId } },
        });
        if (cancelled) return;
        if (data) {
          setArtifact(data);
          setDraft(data.current.content);
        } else {
          setFailed(true);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  const saved = artifact?.current.content ?? "";
  useEffect(() => {
    if (tab !== "edit" || draft === saved) {
      setLive(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const { data } = await api.POST("/api/artifacts/{artifact_id}/validate", {
            params: { path: { artifact_id: artifactId } },
            body: { content: draft },
          });
          if (!cancelled && data) setLive(data);
        } catch {
          // Saving reports any problem; live checks are a convenience.
        }
      })();
    }, validateDelayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [tab, draft, saved, artifactId, validateDelayMs]);

  async function save() {
    if (!artifact) return;
    setSaving(true);
    setMessage(null);
    try {
      const { data, error } = await api.POST("/api/artifacts/{artifact_id}/versions", {
        params,
        body: { content: draft, base_version: artifact.current_version, note: note.trim() || null },
      });
      if (data) {
        setArtifact(data);
        setDraft(data.current.content);
        setNote("");
        setTab("preview");
        setMessage({ tone: "ok", text: `Saved version ${data.current_version}.` });
      } else {
        setMessage({ tone: "bad", text: detailOf(error) ?? "The version could not be saved." });
      }
    } catch {
      setMessage({ tone: "bad", text: UNREACHABLE });
    } finally {
      setSaving(false);
    }
  }

  async function openVersion(number: number) {
    try {
      const { data } = await api.GET("/api/artifacts/{artifact_id}/versions/{number}", {
        params: { path: { artifact_id: artifactId, number } },
      });
      if (data) {
        setViewing(data);
        setTab("preview");
      }
    } catch {
      setMessage({ tone: "bad", text: UNREACHABLE });
    }
  }

  const back = (
    <button type="button" className="back" onClick={onBack}>
      ← All artifacts
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
  if (!artifact) return <p className="hint">Loading artifact…</p>;

  const current = artifact.current;
  const shown = viewing ?? current;
  const changed = draft !== current.content;
  const refs = citations(shown.content);
  return (
    <article aria-labelledby="artifact-title" className="detail">
      {back}
      <h1 id="artifact-title">{artifact.title}</h1>
      <p className="path">{artifact.path}</p>
      <dl className="facts">
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={artifact.status} />
          </dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>
            {current.number} · {current.origin}
          </dd>
        </div>
        <div>
          <dt>By</dt>
          <dd className="path">{current.actor}</dd>
        </div>
        <div>
          <dt>OKF findings</dt>
          <dd>{current.findings}</dd>
        </div>
      </dl>
      {message && (
        <p role="status" className={`notice notice--${message.tone}`}>
          {message.text}
        </p>
      )}

      <div className="tabs" role="tablist" aria-label="View">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className="tabs__tab"
            onClick={() => {
              setTab(item.id);
              setViewing(null);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="review">
        <div className="review__main">
          {tab === "preview" && (
            <>
              {viewing && (
                <p className="notice">
                  Viewing version {viewing.number} ({viewing.origin} by {viewing.actor}).{" "}
                  <button type="button" className="link" onClick={() => setViewing(null)}>
                    Back to the current version
                  </button>
                </p>
              )}
              <Preview content={shown.content} />
            </>
          )}

          {tab === "edit" && (
            <div className="editor">
              <textarea
                aria-label="Markdown"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                spellCheck={false}
                rows={32}
              />
              <input
                aria-label="Change note"
                placeholder="What did you change? (optional)"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <div className="actions">
                <button type="button" onClick={() => void save()} disabled={!changed || saving}>
                  {saving ? "Saving…" : `Save as version ${artifact.current_version + 1}`}
                </button>
                <button
                  type="button"
                  className="button--secondary"
                  disabled={!changed || saving}
                  onClick={() => {
                    setDraft(current.content);
                    setNote("");
                  }}
                >
                  Discard changes
                </button>
              </div>
              <section className="panel" aria-label="Live findings">
                <h2>Findings for your edit</h2>
                {!changed ? (
                  <p className="hint">No unsaved changes.</p>
                ) : live === null ? (
                  <p className="hint">Checking…</p>
                ) : (
                  <Findings findings={live} />
                )}
              </section>
            </div>
          )}

          {tab === "versions" && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Version</th>
                    <th scope="col">Origin</th>
                    <th scope="col">By</th>
                    <th scope="col">Saved</th>
                    <th scope="col">Note</th>
                    <th scope="col">Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {[...artifact.versions].reverse().map((version) => (
                    <tr key={version.number}>
                      <td>
                        <button
                          type="button"
                          className="link"
                          aria-label={`View version ${version.number}`}
                          onClick={() => void openVersion(version.number)}
                        >
                          v{version.number}
                        </button>
                      </td>
                      <td>
                        <span className={`badge badge--${version.origin === "edited" ? "ok" : "info"}`}>
                          {version.origin}
                        </span>
                      </td>
                      <td className="path">{version.actor}</td>
                      <td>{new Date(version.created_at).toLocaleString()}</td>
                      <td>{version.note ?? "—"}</td>
                      <td>{version.findings}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="review__side">
          <section className="panel" aria-label="Citations">
            <h2>Citations</h2>
            {refs.length === 0 ? (
              <p className="hint">No citations.</p>
            ) : (
              <ul className="citations">
                {refs.map((ref) => (
                  <li key={ref.label}>
                    <code>{ref.label.toUpperCase()}</code>{" "}
                    {ref.url?.startsWith("http") ? (
                      <a href={ref.url} target="_blank" rel="noopener noreferrer">
                        {ref.title}
                      </a>
                    ) : (
                      <span>{ref.title}</span>
                    )}
                    {ref.url && !ref.url.startsWith("http") && (
                      <span className="path citations__path">{ref.url}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel" aria-label="Findings">
            <h2>OKF findings</h2>
            <Findings findings={shown.finding_details} />
          </section>
        </aside>
      </div>
    </article>
  );
}
