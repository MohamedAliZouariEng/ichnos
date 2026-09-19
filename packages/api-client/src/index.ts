import createClient from "openapi-fetch";
import type { components, paths } from "@ichnos/contracts";

type Schemas = components["schemas"];

export type Health = Schemas["Health"];
export type ServerConfig = Schemas["ServerConfig"];
export type Workspace = Schemas["WorkspaceRead"];
export type WorkspaceCreate = Schemas["WorkspaceCreate"];
export type WorkspaceUpdate = Schemas["WorkspaceUpdate"];
export type GitHubAccess = Schemas["GitHubAccess"];

/**
 * Create a typed client for the Ichnos API.
 * fetch is looked up at request time, so tests and other runtimes can replace it.
 */
export function createIchnosClient(baseUrl: string) {
  return createClient<paths>({
    baseUrl,
    fetch: (request) => globalThis.fetch(request),
  });
}

export type IchnosClient = ReturnType<typeof createIchnosClient>;
