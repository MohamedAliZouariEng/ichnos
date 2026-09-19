import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HealthBadge } from "./HealthBadge";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("HealthBadge", () => {
  it("shows a healthy API with its version", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { status: "ok", version: "0.1.0", database: "ok" })),
    );
    render(<HealthBadge />);
    expect(await screen.findByText("API healthy")).toBeInTheDocument();
    expect(screen.getByText("v0.1.0 · database ok")).toBeInTheDocument();
  });

  it("shows a degraded API when the database is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(503, { status: "degraded", version: "0.1.0", database: "unavailable" }),
      ),
    );
    render(<HealthBadge />);
    expect(await screen.findByText("API degraded")).toBeInTheDocument();
  });

  it("shows an unreachable API when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(<HealthBadge />);
    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
  });
});
