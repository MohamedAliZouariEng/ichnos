/** Shapes of the two action payloads (ADR-0015, ADR-0017), as the API stores them. */
export type DocsFile = { path: string; content: string };
export type DocsPayload = {
  kind: "docs_pull_request";
  branch: string;
  base_branch: string;
  title: string;
  body: string;
  files: DocsFile[];
};
export type IssueSpec = { title: string; body: string; labels: string[]; key?: string };
export type IssuesPayload = { kind: "create_issues"; epic: IssueSpec; stories: IssueSpec[] };

export const ACTION_LABEL: Record<string, string> = {
  docs_pull_request: "Docs pull request",
  create_issues: "Issues",
};
