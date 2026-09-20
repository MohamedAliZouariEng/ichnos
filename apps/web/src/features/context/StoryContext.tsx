import { useEffect, useState } from "react";
import type { ContextPack, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";

const ROLES: [string, string][] = [
  ["story", "Story"],
  ["epic", "Epic"],
  ["initiative", "Initiative"],
  ["brd", "Business requirements"],
  ["techspec", "Technical specification"],
  ["adr", "Decisions"],
  ["related", "Related Issues and pull requests"],
  ["code", "Code"],
];
const TRUST: Record<string, [string, string]> = {
  human_verified: ["Human verified", "ok"],
  agent_verified: ["Agent verified", "info"],
  generated: ["Generated", "warn"],
  unknown: ["Unknown", "muted"],
  github: ["GitHub", "info"],
  repository: ["Repository", "info"],
};

type Props = { workspace: Workspace; number: number; onBack: () => void };

/** Everything needed to implement one Story, with provenance and trust (ADR-0019). */
export function StoryContext({ workspace, number, onBack }: Props) {
  const [pack, setPack] = useState<ContextPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data, error: failure } = await api.GET(
          "/api/workspaces/{workspace_id}/stories/{number}/context",
          { params: { path: { workspace_id: workspace.id, number } } },
        );
        if (cancelled) return;
        if (data) setPack(data);
        else setError(detailOf(failure) ?? "The context pack could not be built.");
      } catch {
        if (!cancelled) setError(UNREACHABLE);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspace.id, number]);

  const back = (
    <button type="button" className="back" onClick={onBack}>
      ← GitHub context
    </button>
  );
  if (error) {
    return (
      <>
        {back}
        <p className="notice notice--bad">{error}</p>
      </>
    );
  }
  if (!pack) return <p className="hint">Building the context pack…</p>;

  const story = pack.items.find((item) => item.role === "story");
  return (
    <article aria-labelledby="story-title" className="detail">
      {back}
      <h1 id="story-title">
        Story #{number}
        {story ? `: ${story.title}` : ""}
      </h1>
      <p className="lede">
        Context pack <code>{pack.hash.slice(0, 12)}</code> · {pack.items.length} items, assembled
        from synced knowledge without a model.
      </p>
      {pack.notes.map((note) => (
        <p key={note} className="notice notice--warn">
          {note}
        </p>
      ))}
      {pack.absent.length > 0 && (
        <p className="notice">Not found for this Story: {pack.absent.join(", ")}.</p>
      )}
      {ROLES.map(([role, label]) => {
        const items = pack.items.filter((item) => item.role === role);
        if (items.length === 0) return null;
        return (
          <section key={role} className="panel" aria-label={label}>
            <h2>{label}</h2>
            {items.map((item) => {
              const [trust, tone] = TRUST[item.trust] ?? [item.trust, "muted"];
              return (
                <div key={item.id} className="pack-item">
                  <p>
                    <code>{item.id}</code>{" "}
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noopener noreferrer">
                        {item.title}
                      </a>
                    ) : (
                      <strong>{item.title}</strong>
                    )}{" "}
                    <span className={`badge badge--${tone}`}>{trust}</span>
                    {item.flags.map((flag) => (
                      <span key={flag} className="badge badge--warn">
                        {flag}
                      </span>
                    ))}
                  </p>
                  <p className="hint">
                    <span className="path">{item.source}</span> · {item.reason}
                  </p>
                  {item.excerpt && (
                    <details>
                      <summary>Excerpt</summary>
                      <pre className="payload-text">{item.excerpt}</pre>
                    </details>
                  )}
                </div>
              );
            })}
          </section>
        );
      })}
    </article>
  );
}
