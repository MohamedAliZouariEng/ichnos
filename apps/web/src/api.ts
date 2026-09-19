import { createIchnosClient } from "@ichnos/api-client";

// Same origin: Vite proxies /api in development; nginx does it in Docker.
export const api = createIchnosClient(window.location.origin);
