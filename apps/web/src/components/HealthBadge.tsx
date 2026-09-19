import { useEffect, useState } from "react";
import type { Health } from "@ichnos/api-client";

import { api } from "../api";

type HealthState =
  | { kind: "checking" }
  | { kind: "ok"; health: Health }
  | { kind: "degraded"; health: Health }
  | { kind: "offline" };

const LABELS: Record<HealthState["kind"], string> = {
  checking: "Checking API…",
  ok: "API healthy",
  degraded: "API degraded",
  offline: "API unreachable",
};

export function useHealth(intervalMs = 15_000): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const { data, error } = await api.GET("/healthz");
        if (cancelled) return;
        if (data) setState({ kind: "ok", health: data });
        else if (error) setState({ kind: "degraded", health: error });
        else setState({ kind: "offline" });
      } catch {
        if (!cancelled) setState({ kind: "offline" });
      }
    }
    void check();
    const timer = window.setInterval(() => void check(), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return state;
}

export function HealthBadge() {
  const state = useHealth();
  let detail = "";
  if (state.kind === "ok" || state.kind === "degraded") {
    detail = `v${state.health.version} · database ${state.health.database}`;
  } else if (state.kind === "offline") {
    detail = "Check that the API service is running";
  }
  return (
    <div className={`health health--${state.kind}`} role="status" aria-live="polite">
      <span className="health__dot" aria-hidden="true" />
      <span className="health__label">{LABELS[state.kind]}</span>
      {detail && <span className="health__detail">{detail}</span>}
    </div>
  );
}
