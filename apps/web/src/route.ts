import { useCallback, useEffect, useState } from "react";

export type Section = "workspace" | "inbox" | "github" | "runs" | "artifacts" | "approvals" | "traceability" | "questions";
export type Route = {
  section: Section;
  doc?: string | undefined;
  run?: string | undefined;
  artifact?: string | undefined;
  approval?: string | undefined;
  story?: string | undefined;
  brd?: string | undefined;
  answer?: string | undefined;
};

const SECTIONS: readonly Section[] = [
  "workspace",
  "inbox",
  "github",
  "runs",
  "artifacts",
  "approvals",
  "traceability",
  "questions",
];

export function parseRoute(hash: string): Route {
  const [name = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const section = SECTIONS.includes(name as Section) ? (name as Section) : "workspace";
  const params = new URLSearchParams(query);
  return {
    section,
    doc: params.get("doc") ?? undefined,
    run: params.get("run") ?? undefined,
    artifact: params.get("artifact") ?? undefined,
    approval: params.get("approval") ?? undefined,
    story: params.get("story") ?? undefined,
    brd: params.get("brd") ?? undefined,
    answer: params.get("answer") ?? undefined,
  };
}

export function routeHash(route: Route): string {
  const params = new URLSearchParams();
  if (route.doc) params.set("doc", route.doc);
  if (route.run) params.set("run", route.run);
  if (route.artifact) params.set("artifact", route.artifact);
  if (route.approval) params.set("approval", route.approval);
  if (route.story) params.set("story", route.story);
  if (route.brd) params.set("brd", route.brd);
  if (route.answer) params.set("answer", route.answer);
  const query = params.toString();
  return `#/${route.section}${query ? `?${query}` : ""}`;
}

/** The current route, kept in the URL hash so a reload returns to the same place. */
export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: Route) => {
    window.location.hash = routeHash(next);
  }, []);
  return [route, navigate];
}
