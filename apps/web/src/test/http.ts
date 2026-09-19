import { vi } from "vitest";

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (request: Request) => Response | Promise<Response>;

/** Replace fetch with a router keyed by "METHOD /path". Unknown requests fail the test. */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (request: Request) => {
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const handler = routes[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    return handler(request);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
