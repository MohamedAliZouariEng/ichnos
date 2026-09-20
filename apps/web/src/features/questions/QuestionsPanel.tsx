import { type FormEvent, useEffect, useState } from "react";
import type { AnswerRead, AnswerSummary, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

type Props = {
  workspace: Workspace;
  answerId?: string | undefined;
  onOpenAnswer: (answerId: string) => void;
};

function AnswerView({ answer }: { answer: AnswerRead }) {
  const byId = new Map(answer.sources.map((s) => [s.id, s]));
  return (
    <article aria-label="Answer">
      <h2>{answer.question}</h2>
      <p className="hint">
        {answer.model === "none" ? "No model call: nothing was retrieved." : `Answered by ${answer.model}`} ·{" "}
        {answer.tokens} tokens · {new Date(answer.created_at).toLocaleString()}
      </p>
      <section className="panel" aria-label="Statements">
        {answer.statements.length === 0 && <p className="empty">No statement could be grounded.</p>}
        <ul className="statements">
          {answer.statements.map((statement) => (
            <li key={statement.text}>
              {statement.text}{" "}
              {statement.cites.map((sid) => {
                const source = byId.get(sid);
                return source?.url ? (
                  <a key={sid} className="chip" href={source.url} target="_blank" rel="noopener noreferrer"
                     title={source.locator}>
                    {sid}
                  </a>
                ) : (
                  <span key={sid} className="chip" title={source?.locator}>
                    {sid}
                  </span>
                );
              })}
            </li>
          ))}
        </ul>
      </section>
      {answer.gaps.length > 0 && (
        <section className="notice notice--warn" aria-label="Gaps">
          <strong>Gaps</strong>
          <ul>
            {answer.gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel" aria-label="Sources">
        <h3>Sources</h3>
        <ul className="sources">
          {answer.sources.map((source) => (
            <li key={source.id} className={answer.cited.includes(source.id) ? "source--cited" : ""}>
              <code>{source.id}</code> {source.kind} ·{" "}
              {source.url ? (
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.locator}
                </a>
              ) : (
                source.locator
              )}{" "}
              <span className="badge badge--info">{source.trust.replace("_", " ")}</span>
              {source.flags.map((flag) => (
                <span key={flag} className="badge badge--warn">
                  {flag}
                </span>
              ))}
              {answer.cited.includes(source.id) && <span className="badge badge--ok">cited</span>}
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

/** Ask about the project; every statement cites its sources and gaps are stated (ADR-0024). */
export function QuestionsPanel({ workspace, answerId, onOpenAnswer }: Props) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerRead | null>(null);
  const [history, setHistory] = useState<AnswerSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/questions", {
          params: { path: { workspace_id: workspace.id } },
        });
        setHistory(data ?? []);
      } catch {
        setError(UNREACHABLE);
      }
    })();
  }, [workspace.id, answer?.id]);

  useEffect(() => {
    if (!answerId || answer?.id === answerId) return;
    void (async () => {
      const { data } = await api.GET("/api/answers/{answer_id}", {
        params: { path: { answer_id: answerId } },
      });
      if (data) setAnswer(data);
    })();
  }, [answerId, answer?.id]);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/workspaces/{workspace_id}/questions", {
        params: { path: { workspace_id: workspace.id } },
        body: { question },
      });
      if (data) {
        setAnswer(data);
        onOpenAnswer(data.id);
      } else {
        setError(detailOf(failure) ?? "The question could not be answered.");
      }
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="questions-title">
      <h1 id="questions-title">Questions</h1>
      <p className="lede">
        Ask about {workspace.repository}. Every statement cites its sources, and what the sources do
        not show is listed as a gap.
      </p>
      <form className="panel" onSubmit={(event) => void ask(event)}>
        <label htmlFor="question">Question</label>
        <textarea id="question" rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} />
        <p className="hint">
          Asking sends the question and the retrieved sources to the configured model. Nothing is
          written to GitHub.
        </p>
        <button type="submit" disabled={busy || question.trim().length < 3}>
          {busy ? "Answering…" : "Ask"}
        </button>
        {error && (
          <p role="alert" className="text-bad">
            {error}
          </p>
        )}
      </form>
      {answer && <AnswerView answer={answer} />}
      {history.length > 0 && (
        <section className="panel" aria-label="Earlier questions">
          <h3>Earlier questions</h3>
          <ul>
            {history.map((item) => (
              <li key={item.id}>
                <button type="button" className="link" onClick={() => onOpenAnswer(item.id)}>
                  {item.question}
                </button>{" "}
                <span className="hint">
                  {item.statements} statements · {item.gaps} gaps
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
