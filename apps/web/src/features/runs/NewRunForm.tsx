import { type ChangeEvent, useEffect, useState } from "react";
import type { DocumentSummary, ServerConfig, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { ModelNotice } from "../../components/ModelNotice";
import { UNREACHABLE, detailOf } from "../../labels";

const PASTE = "__paste__";
const UPLOAD = "__upload__";

type Props = { workspace: Workspace; onStarted: (runId: string) => void };

/** Choose a source, then create it and start the requirements workflow in one step. */
export function NewRunForm({ workspace, onStarted }: Props) {
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [notes, setNotes] = useState<DocumentSummary[]>([]);
  const [choice, setChoice] = useState(PASTE);
  const [text, setText] = useState("");
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { workspace_id: workspace.id };

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [server, documents] = await Promise.all([
          api.GET("/api/config"),
          api.GET("/api/workspaces/{workspace_id}/documents", { params: { path } }),
        ]);
        if (cancelled) return;
        setConfig(server.data ?? null);
        const meetingNotes = (documents.data ?? []).filter((doc) => doc.type === "Meeting Note");
        setNotes(meetingNotes);
        if (meetingNotes[0]) setChoice(meetingNotes[0].path);
      } catch {
        if (!cancelled) setError(UNREACHABLE);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.id]);

  async function readFile(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    setFile(chosen ? { name: chosen.name, content: await chosen.text() } : null);
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      let sourceId: string | undefined;
      let failure: unknown = null;
      if (choice === PASTE) {
        const saved = await api.POST("/api/workspaces/{workspace_id}/sources", {
          params: { path },
          body: { kind: "pasted", content: text },
        });
        sourceId = saved.data?.id;
        failure = saved.error;
      } else if (choice === UPLOAD && file) {
        const saved = await api.POST("/api/workspaces/{workspace_id}/sources", {
          params: { path },
          body: { kind: "upload", filename: file.name, content: file.content },
        });
        sourceId = saved.data?.id;
        failure = saved.error;
      } else {
        const saved = await api.POST("/api/workspaces/{workspace_id}/sources/from-document", {
          params: { path },
          body: { path: choice },
        });
        sourceId = saved.data?.id;
        failure = saved.error;
      }
      if (!sourceId) {
        setError(detailOf(failure) ?? "The source could not be saved.");
        return;
      }
      const run = await api.POST("/api/workspaces/{workspace_id}/runs", {
        params: { path },
        body: { workflow: "requirements", source_ids: [sourceId] },
      });
      if (!run.data) {
        setError(detailOf(run.error) ?? "The run could not start.");
        return;
      }
      onStarted(run.data.id);
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  const ready = choice === PASTE ? text.trim() !== "" : choice === UPLOAD ? file !== null : true;
  return (
    <section className="panel" aria-labelledby="new-run-title">
      <h2 id="new-run-title">Draft a BRD</h2>
      <ModelNotice config={config} />
      <div className="field">
        <label htmlFor="run-source">Source</label>
        <select id="run-source" value={choice} onChange={(event) => setChoice(event.target.value)}>
          {notes.map((note) => (
            <option key={note.path} value={note.path}>
              {note.title ?? note.path} (synced meeting note)
            </option>
          ))}
          <option value={PASTE}>Paste text…</option>
          <option value={UPLOAD}>Upload a .md or .txt file…</option>
        </select>
      </div>
      {choice === PASTE && (
        <textarea
          aria-label="Meeting note text"
          rows={10}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Paste the meeting note or product brief here."
        />
      )}
      {choice === UPLOAD && (
        <input
          type="file"
          accept=".md,.markdown,.txt"
          aria-label="Meeting note file"
          onChange={(event) => void readFile(event)}
        />
      )}
      <div className="actions">
        <button
          type="button"
          onClick={() => void start()}
          disabled={busy || !ready || !config?.llm_configured}
        >
          {busy ? "Starting…" : "Draft BRD"}
        </button>
        {error && (
          <span role="status" className="text-bad">
            {error}
          </span>
        )}
      </div>
    </section>
  );
}
