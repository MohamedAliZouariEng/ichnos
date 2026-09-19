import { useEffect, useState } from "react";
import { diffLines } from "diff";
import type { ArtifactVersion, ArtifactVersionSummary } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE } from "../../labels";

const CONTEXT = 3;

type Line = { kind: "add" | "del" | "same"; text: string } | { kind: "gap"; count: number };

function lines(value: string): string[] {
  const split = value.split("\n");
  if (split[split.length - 1] === "") split.pop();
  return split;
}

/** Line diff with long unchanged stretches collapsed, as in `git diff`. */
export function compare(before: string, after: string): { rows: Line[]; added: number; removed: number } {
  const rows: Line[] = [];
  let added = 0;
  let removed = 0;
  for (const part of diffLines(before, after)) {
    const text = lines(part.value);
    if (part.added) {
      added += text.length;
      rows.push(...text.map((line) => ({ kind: "add" as const, text: line })));
    } else if (part.removed) {
      removed += text.length;
      rows.push(...text.map((line) => ({ kind: "del" as const, text: line })));
    } else if (text.length > CONTEXT * 2 + 1) {
      rows.push(...text.slice(0, CONTEXT).map((line) => ({ kind: "same" as const, text: line })));
      rows.push({ kind: "gap", count: text.length - CONTEXT * 2 });
      rows.push(...text.slice(-CONTEXT).map((line) => ({ kind: "same" as const, text: line })));
    } else {
      rows.push(...text.map((line) => ({ kind: "same" as const, text: line })));
    }
  }
  return { rows, added, removed };
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

type Props = {
  artifactId: string;
  versions: ArtifactVersionSummary[];
  current: ArtifactVersion;
};

export function VersionDiff({ artifactId, versions, current }: Props) {
  const [from, setFrom] = useState(versions[0]?.number ?? current.number);
  const [to, setTo] = useState(current.number);
  const [contents, setContents] = useState<Record<number, string>>({
    [current.number]: current.content,
  });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const missing = [from, to].filter((number) => contents[number] === undefined);
    if (missing.length === 0) return;
    let cancelled = false;
    async function load() {
      try {
        const loaded = await Promise.all(
          missing.map(async (number) => {
            const { data } = await api.GET("/api/artifacts/{artifact_id}/versions/{number}", {
              params: { path: { artifact_id: artifactId, number } },
            });
            return [number, data?.content ?? ""] as const;
          }),
        );
        if (!cancelled) setContents((known) => ({ ...known, ...Object.fromEntries(loaded) }));
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [artifactId, from, to, contents]);

  const label = (number: number) => {
    const version = versions.find((item) => item.number === number);
    return `v${number} · ${version?.origin ?? ""}`;
  };
  const before = contents[from];
  const after = contents[to];

  return (
    <section aria-label="Changes" className="changes">
      <div className="changes__pick">
        <label>
          From{" "}
          <select value={from} onChange={(event) => setFrom(Number(event.target.value))}>
            {versions.map((version) => (
              <option key={version.number} value={version.number}>
                {label(version.number)}
              </option>
            ))}
          </select>
        </label>
        <label>
          To{" "}
          <select value={to} onChange={(event) => setTo(Number(event.target.value))}>
            {versions.map((version) => (
              <option key={version.number} value={version.number}>
                {label(version.number)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {failed && <p className="notice notice--bad">{UNREACHABLE}</p>}
      {!failed && from === to && <p className="hint">Choose two different versions to compare.</p>}
      {!failed && from !== to && (before === undefined || after === undefined) && (
        <p className="hint">Loading versions…</p>
      )}
      {!failed && from !== to && before !== undefined && after !== undefined && (() => {
        const { rows, added, removed } = compare(before, after);
        return (
          <>
            <p className="changes__summary">
              {added === 0 && removed === 0
                ? "No differences."
                : `${plural(added, "line")} added, ${plural(removed, "line")} removed`}
            </p>
            <div className="diff" role="table" aria-label={`Changes from v${from} to v${to}`}>
              {rows.map((row, index) =>
                row.kind === "gap" ? (
                  <div key={index} className="diff__gap">
                    ⋯ {plural(row.count, "unchanged line")}
                  </div>
                ) : (
                  <div key={index} className={`diff__line diff__line--${row.kind}`}>
                    <span className="diff__sign" aria-hidden="true">
                      {row.kind === "add" ? "+" : row.kind === "del" ? "−" : " "}
                    </span>
                    <span className="diff__text">{row.text}</span>
                  </div>
                ),
              )}
            </div>
          </>
        );
      })()}
    </section>
  );
}
