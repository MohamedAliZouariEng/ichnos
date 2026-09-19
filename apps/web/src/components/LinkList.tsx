import type { KnowledgeLink } from "@ichnos/api-client";

import { nodeLabel } from "../labels";

type Props = {
  title: string;
  links: KnowledgeLink[];
  direction: "outgoing" | "incoming";
  onOpenDocument: (path: string) => void;
};

/** Links in one direction, with relation, origin, confidence and evidence (ADR-0010). */
export function LinkList({ title, links, direction, onOpenDocument }: Props) {
  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      {links.length === 0 ? (
        <p className="hint">None.</p>
      ) : (
        <ul className="links">
          {links.map((link, index) => {
            const kind = direction === "outgoing" ? link.target_kind : link.source_kind;
            const key = direction === "outgoing" ? link.target_key : link.source_key;
            const other =
              kind === "document" && link.resolved ? (
                <button type="button" className="link" onClick={() => onOpenDocument(key)}>
                  {key}
                </button>
              ) : (
                <span className="links__node">{nodeLabel(kind, key)}</span>
              );
            return (
              <li key={`${link.relation}:${kind}:${key}:${index}`} className="links__item">
                <div className="links__head">
                  {direction === "incoming" && other}
                  <span className="links__relation">{link.relation}</span>
                  {direction === "outgoing" && other}
                  {link.origin === "explicit" ? (
                    <span className="badge badge--ok">explicit</span>
                  ) : (
                    <span className="badge badge--info">
                      inferred · {Math.round(link.confidence * 100)}%
                    </span>
                  )}
                  {!link.resolved && <span className="badge badge--muted">not synced</span>}
                </div>
                <p className="links__evidence">{link.evidence}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
