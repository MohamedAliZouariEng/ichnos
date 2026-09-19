import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi } from "../test/http";
import { ModelNotice } from "./ModelNotice";

const BASE = {
  github_token_configured: true,
  llm_provider: "openai-compatible",
  llm_model: "gemini-3.8-flash",
  llm_configured: true,
  llm_host: "generativelanguage.googleapis.com",
  llm_local: false,
  llm_reasoning_effort: "low",
  embedding_provider: null,
  embedding_model: null,
};

describe("ModelNotice", () => {
  it("warns that content leaves the machine for a hosted provider", () => {
    render(<ModelNotice config={BASE} />);
    expect(screen.getByText("gemini-3.8-flash")).toBeInTheDocument();
    expect(screen.getByText(/are sent to generativelanguage.googleapis.com/)).toBeInTheDocument();
  });

  it("says a local model stays on this machine", () => {
    render(<ModelNotice config={{ ...BASE, llm_model: "qwen3:4b", llm_host: "ollama", llm_local: true }} />);
    expect(screen.getByText(/on this machine/)).toBeInTheDocument();
    expect(screen.queryByText(/are sent to/)).not.toBeInTheDocument();
  });

  it("explains what to set when no model is configured", () => {
    render(<ModelNotice config={{ ...BASE, llm_configured: false }} />);
    expect(screen.getByText(/No model is configured/)).toBeInTheDocument();
  });

  it("runs the model check and shows its result", async () => {
    mockApi({
      "POST /api/config/model-check": () =>
        jsonResponse(200, {
          ok: true, provider: "openai-compatible", model: "gemini-3.8-flash", local: false,
          message: "The model answered with valid structured output.",
          total_tokens: 25, latency_ms: 1537,
        }),
    });
    render(<ModelNotice config={BASE} />);
    fireEvent.click(screen.getByRole("button", { name: "Check model" }));
    expect(await screen.findByText(/valid structured output\. \(1537 ms, 25 tokens\)/)).toBeInTheDocument();
  });
});
