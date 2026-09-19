import createClient from "openapi-fetch";
import type { components, paths } from "@ichnos/contracts";

type Schemas = components["schemas"];

export type Health = Schemas["Health"];
export type ServerConfig = Schemas["ServerConfig"];
export type Workspace = Schemas["WorkspaceRead"];
export type WorkspaceCreate = Schemas["WorkspaceCreate"];
export type WorkspaceUpdate = Schemas["WorkspaceUpdate"];
export type GitHubAccess = Schemas["GitHubAccess"];

/** Create a typed client. An empty baseUrl calls the API on the same origin. */
export function createIchnosClient(baseUrl = "") {
  return createClient<paths>({ baseUrl });
}

export type IchnosClient = ReturnType<typeof createIchnosClient>;
