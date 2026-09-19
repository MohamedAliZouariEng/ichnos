import { type FormEvent, useState } from "react";
import type { SearchHit } from "@ichnos/api-client";

import { api } from "../../api";
import { Highlighted } from "../../components/Highlighted";
import { UNREACHABLE, nodeLabel } from "../../labels";

type Props = { workspaceId: string; onOpenDocument: (path: string) => void };

export function SearchBox({ workspaceId, onOpenDocument }: Props) {
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    setError(null);
    if (!q) {
      setHits(null);
      return;
    }
    try {
      const { data } = await api.GET("/api/workspaces/{workspace_id}/search", {
        params: { path: { workspace_id: workspaceId }, query: { q, limit: 8 } },
      });
      setSearched(q);
      setHits(data ?? []);
    } catch {
      setError(UNREACHABLE);
    }
  }

  return (
    <div className="search">
      <form role="search" className="search__form" onSubmit={(event) => void search(event)}>
        <label htmlFor="search-input" className="visually-hidden">
          Search this workspace
        </label>
        <input
          id="search-input"
          type="search"
          placeholder="Search documents, Issues, pull requests and commits"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" className="button--secondary">
          Search
        </button>
      </form>
      {error && <p className="notice notice--bad">{error}</p>}
      {hits && hits.length === 0 && <p className="hint">No matches for “{searched}”.</p>}
      {hits && hits.length > 0 && (
        <ol className="hits" aria-label={`Results for ${searched}`}>
          {hits.map((hit, index) => (
            <li key={`${hit.source_kind}:${hit.source_key}:${index}`} className="hits__item">
              <div className="hits__head">
                {hit.source_kind === "document" ? (
                  <button
                    type="button"
                    className="link"
                    onClick={() => onOpenDocument(hit.source_key)}
                  >
                    {hit.title ?? hit.source_key}
                  </button>
                ) : (
                  <span className="hits__title">
                    {nodeLabel(hit.source_kind, hit.source_key)}
                    {hit.title && hit.source_kind !== "commit" ? ` · ${hit.title}` : ""}
                  </span>
                )}
                {hit.heading && <span className="hits__heading">{hit.heading}</span>}
              </div>
              <p className="hits__snippet">
                <Highlighted snippet={hit.snippet} />
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
