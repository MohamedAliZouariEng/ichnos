import { useEffect, useState } from "react";
import type { RunDetail, RunEvent } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE } from "../../labels";
import { StatusBadge } from "./StatusBadge";

const STAGES = [
  { name: "retrieval", label: "Retrieval" },
  { name: "requirements", label: "Requirements" },
  { name: "specification", label: "Specification" },
];
const STATE_LABEL = { pending: "Waiting", running: "Running…", done: "Done", failed: "Failed" };
const FINAL_EVENTS = new Set(["run.completed", "run.failed", "run.interrupted"]);
const TERMINAL = new Set(["succeeded", "failed", "interrupted"]);

type StageState = { state: keyof typeof STATE_LABEL; message: string; ms?: number | undefined };

function stageState(events: RunEvent[], name: string): StageState {
  let current: StageState = { state: "pending", message: "" };
  for (const event of events) {
    if (event.stage !== name) continue;
    const ms = typeof event.data.duration_ms === "number" ? event.data.duration_ms : undefined;
    if (event.kind === "stage.started") current = { state: "running", message: "" };
    if (event.kind === "stage.completed") current = { state: "done", message: event.message, ms };
    if (event.kind === "stage.failed") current = { state: "failed", message: event.message, ms };
  }
  return current;
}

type Props = { runId: string; onBack: () => void; pollMs?: number | undefined };

export function RunDetailsView({ runId, onBack, pollMs = 2000 }: Props) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let stream: EventSource | null = null;
    let timer: number | undefined;

    async function load(): Promise<RunDetail | null> {
      try {
        const { data } = await api.GET("/api/runs/{run_id}", {
          params: { path: { run_id: runId } },
        });
        if (!cancelled && data) {
          setRun(data);
          setEvents(data.events);
        }
        return data ?? null;
      } catch {
        if (!cancelled) setFailed(true);
        return null;
      }
    }

    async function follow() {
      const first = await load();
      if (cancelled || !first || TERMINAL.has(first.status)) return;
      if (typeof window.EventSource === "function") {
        const after = first.events[first.events.length - 1]?.id ?? 0;
        stream = new EventSource(`/api/runs/${runId}/events?after=${after}`);
        stream.onmessage = (message: MessageEvent<string>) => {
          const event = JSON.parse(message.data) as RunEvent;
          setEvents((current) =>
            current.some((known) => known.id === event.id) ? current : [...current, event],
          );
          if (FINAL_EVENTS.has(event.kind)) {
            stream?.close();
            void load();
          }
        };
      } else {
        const poll = async () => {
          const latest = await load();
          if (!cancelled && latest && !TERMINAL.has(latest.status)) {
            timer = window.setTimeout(() => void poll(), pollMs);
          }
        };
        timer = window.setTimeout(() => void poll(), pollMs);
      }
    }

    void follow();
    return () => {
      cancelled = true;
      stream?.close();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runId, pollMs]);

  const back = (
    <button type="button" className="back" onClick={onBack}>
      ← All runs
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
  if (!run) return <p className="hint">Loading run…</p>;

  const result = (run.outputs.result ?? {}) as {
    path?: string;
    version?: number;
    requirements?: number;
    findings?: number;
  };
  return (
    <article aria-labelledby="run-title" className="detail">
      {back}
      <h1 id="run-title">Requirements run</h1>
      <p className="path">{run.id}</p>
      <dl className="facts">
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={run.status} />
          </dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{new Date(run.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>{run.total_tokens}</dd>
        </div>
      </dl>

      <ol className="stages" aria-label="Stages">
        {STAGES.map((stage) => {
          const state = stageState(events, stage.name);
          return (
            <li key={stage.name} className={`stage stage--${state.state}`}>
              <span className="stage__name">{stage.label}</span>
              <span className="stage__state">
                {STATE_LABEL[state.state]}
                {state.ms !== undefined && ` · ${(state.ms / 1000).toFixed(1)} s`}
              </span>
              {state.message && <p className="stage__message">{state.message}</p>}
            </li>
          );
        })}
      </ol>

      {run.error && <p className="notice notice--bad">{run.error}</p>}

      {run.artifact_id && (
        <section className="panel" aria-label="Draft BRD">
          <h2>Draft BRD</h2>
          <p>
            <span className="path">{result.path}</span> · version {result.version ?? 1} ·{" "}
            {result.requirements ?? 0} requirements · {result.findings ?? 0} OKF findings
          </p>
        </section>
      )}

      <section className="panel" aria-label="Event log">
        <h2>Event log</h2>
        <ol className="events">
          {events.map((event) => (
            <li key={event.id}>
              <span className="events__time">{new Date(event.created_at).toLocaleTimeString()}</span>{" "}
              <code>{event.kind}</code> {event.message}
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}
