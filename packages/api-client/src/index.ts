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

export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type SyncRun = Schemas["SyncRunRead"];
export type GitHubItem = Schemas["GitHubItemSummary"];
export type KnowledgeLink = Schemas["LinkRead"];
export type SearchHit = Schemas["SearchHit"];
export type ModelCheck = Schemas["ModelCheck"];
export type SourceRead = Schemas["SourceRead"];
export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type RunEvent = Schemas["RunEventRead"];
