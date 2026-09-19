import { useState } from "react";
import type { ModelCheck, ServerConfig } from "@ichnos/api-client";

import { api } from "../api";
import { UNREACHABLE } from "../labels";

/** Which model runs workflows, and whether content leaves this machine (ADR-0006, ADR-0012). */
export function ModelNotice({ config }: { config: ServerConfig | null }) {
  const [check, setCheck] = useState<ModelCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!config?.llm_configured) {
    return (
      <p className="notice notice--warn">
        No model is configured. Set ICHNOS_LLM_PROVIDER, ICHNOS_LLM_BASE_URL, ICHNOS_LLM_MODEL and,
        for hosted providers, ICHNOS_LLM_API_KEY in .env, then restart the API.
      </p>
    );
  }

  async function runCheck() {
    setChecking(true);
    setError(null);
    try {
      const { data } = await api.POST("/api/config/model-check");
      setCheck(data ?? null);
    } catch {
      setError(UNREACHABLE);
    } finally {
      setChecking(false);
    }
  }

  const local = config.llm_local;
  const host = config.llm_host ?? "this machine";
  return (
    <div className={local ? "notice notice--ok" : "notice notice--warn"} role="note">
      <p>
        Workflows use <strong>{config.llm_model ?? config.llm_provider}</strong>
        {local ? " on this machine." : <> at <span className="path">{host}</span>.</>}
      </p>
      {!local && (
        <p>
          When a workflow runs, the meeting note and the repository content it retrieves are sent
          to {host}. Check that provider’s terms before using private repositories.
        </p>
      )}
      <div className="actions">
        <button
          type="button"
          className="button--secondary"
          onClick={() => void runCheck()}
          disabled={checking}
        >
          {checking ? "Checking…" : "Check model"}
        </button>
        {check && (
          <span role="status" className={check.ok ? "hint" : "text-bad"}>
            {check.message}
            {check.ok && ` (${check.latency_ms} ms, ${check.total_tokens} tokens)`}
          </span>
        )}
        {error && (
          <span role="status" className="text-bad">
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
