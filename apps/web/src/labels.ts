export const UNREACHABLE = "Could not reach the API. Check that it is running, then try again.";

/** The API's own explanation from an error response, if it sent one. */
export function detailOf(error: unknown): string | null {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return null;
}

/** A short human name for a node in the knowledge graph. */
export function nodeLabel(kind: string, key: string): string {
  if (kind === "issue") return `Issue #${key}`;
  if (kind === "pull_request") return `PR #${key}`;
  if (kind === "commit") return `Commit ${key.slice(0, 7)}`;
  return key;
}
