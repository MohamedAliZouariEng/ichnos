import { useEffect, useState } from "react";
import type { GitHubItem, KnowledgeLink, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { LinkList } from "../../components/LinkList";
import { UNREACHABLE } from "../../labels";

type Filter = "all" | "issue" | "pull_request";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "issue", label: "Issues" },
  { id: "pull_request", label: "Pull requests" },
];

type Props = {
  workspace: Workspace;
  onOpenDocument: (path: string) => void;
  onOpenStory?: ((number: number) => void) | undefined;
};

function stateOf(item: GitHubItem): { label: string; tone: string } {
  if (item.type === "pull_request" && item.merged_at) return { label: "merged", tone: "info" };
  if (item.state === "open") return { label: "open", tone: "ok" };
  return { label: "closed", tone: "muted" };
}

type ItemLinksProps = {
  workspaceId: string;
  item: GitHubItem;
  onOpenDocument: (path: string) => void;
};

function ItemLinks({ workspaceId, item, onOpenDocument }: ItemLinksProps) {
  const [links, setLinks] = useState<KnowledgeLink[] | null>(null);
  const [failed, setFailed] = useState(false);
  const key = String(item.number);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/links", {
          params: { path: { workspace_id: workspaceId }, query: { kind: item.type, key } },
        });
        if (!cancelled) setLinks(data ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, item.type, key]);

  if (failed) return <p className="notice notice--bad">{UNREACHABLE}</p>;
  if (links === null) return <p className="hint">Loading links…</p>;
  const isNode = (kind: string, value: string) => kind === item.type && value === key;
  return (
    <div className="item__links">
      <LinkList
        title={`Links from #${item.number}`}
        links={links.filter((l) => isNode(l.source_kind, l.source_key))}
        direction="outgoing"
        onOpenDocument={onOpenDocument}
      />
      <LinkList
        title={`Links to #${item.number}`}
        links={links.filter((l) => isNode(l.target_kind, l.target_key))}
        direction="incoming"
        onOpenDocument={onOpenDocument}
      />
    </div>
  );
}

export function GitHubPanel({ workspace, onOpenDocument, onOpenStory }: Props) {
  const [items, setItems] = useState<GitHubItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/github/items", {
          params: { path: { workspace_id: workspace.id } },
        });
        if (!cancelled) setItems(data ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspace.id]);

  const visible = (items ?? []).filter((item) => filter === "all" || item.type === filter);
  return (
    <section aria-labelledby="github-context-title">
      <h1 id="github-context-title">GitHub context</h1>
      <p className="lede">Issues and pull requests synced from {workspace.repository}.</p>

      {failed && <p className="notice notice--bad">{UNREACHABLE}</p>}
      {!failed && items === null && <p className="hint">Loading Issues and pull requests…</p>}
      {items !== null && items.length === 0 && (
        <p className="empty">
          No Issues or pull requests synced yet. Open the <strong>Inbox</strong> and select{" "}
          <strong>Sync now</strong>.
        </p>
      )}

      {items !== null && items.length > 0 && (
        <>
          <div className="filters" role="group" aria-label="Show">
            {FILTERS.map((option) => (
              <button
                key={option.id}
                type="button"
                className="filters__button"
                aria-pressed={filter === option.id}
                onClick={() => setFilter(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <ul className="items">
            {visible.map((item) => {
              const state = stateOf(item);
              const open = expanded === item.number;
              return (
                <li key={item.number} className="item">
                  <div className="item__head">
                    <span className="item__number">
                      {item.type === "pull_request" ? "PR" : "Issue"} #{item.number}
                    </span>
                    <span className="item__title">{item.title}</span>
                    <span className={`badge badge--${state.tone}`}>{state.label}</span>
                  </div>
                  <div className="item__meta">
                    {item.labels.map((label) => (
                      <span key={label} className="chip">
                        {label}
                      </span>
                    ))}
                    <span>
                      {item.author ?? "unknown"} · updated{" "}
                      {new Date(item.updated_at).toLocaleDateString()}
                    </span>
                    <a href={item.url} target="_blank" rel="noopener noreferrer">
                      Open on GitHub
                    </a>
                    <button
                      type="button"
                      className="link"
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : item.number)}
                    >
                      {open ? "Hide links" : "Show links"}
                    </button>
                    {item.type !== "pull_request" && onOpenStory && (
                      <button type="button" className="link" onClick={() => onOpenStory(item.number)}>
                        Context pack
                      </button>
                    )}
                  </div>
                  {open && (
                    <ItemLinks
                      workspaceId={workspace.id}
                      item={item}
                      onOpenDocument={onOpenDocument}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
