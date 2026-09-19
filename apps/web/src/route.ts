import { useCallback, useEffect, useState } from "react";

export type Section = "workspace" | "inbox" | "github";
export type Route = { section: Section; doc?: string | undefined };

export function parseRoute(hash: string): Route {
  const [name = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const section: Section = name === "inbox" || name === "github" ? name : "workspace";
  const doc = new URLSearchParams(query).get("doc") ?? undefined;
  return { section, doc };
}

export function routeHash(route: Route): string {
  const query = route.doc ? `?doc=${encodeURIComponent(route.doc)}` : "";
  return `#/${route.section}${query}`;
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
