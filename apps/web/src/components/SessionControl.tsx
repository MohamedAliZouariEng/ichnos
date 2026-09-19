import { type FormEvent, useEffect, useState } from "react";
import type { ApproverSession } from "@ichnos/api-client";

import { api } from "../api";
import { UNREACHABLE, detailOf } from "../labels";

/** Sign in to approve (ADR-0016); shows who approves while signed in. */
export function SessionControl() {
  const [session, setSession] = useState<ApproverSession | null>(null);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/session");
        if (!cancelled && data) setSession(data);
      } catch {
        // The health badge already reports an unreachable API.
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/session", { body: { password } });
      if (data) {
        setSession(data);
        setOpen(false);
      } else {
        setError(detailOf(failure) ?? "Sign-in failed.");
      }
    } catch {
      setError(UNREACHABLE);
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      const { data } = await api.DELETE("/api/session");
      if (data) setSession(data);
    } catch {
      setError(UNREACHABLE);
    }
  }

  if (!session) return null;
  if (!session.approvals_enabled) {
    return <span className="session session--off">Approvals disabled</span>;
  }
  if (session.signed_in) {
    return (
      <span className="session">
        Approver <span className="path">{session.approver}</span>{" "}
        <button type="button" className="link" onClick={() => void signOut()}>
          Sign out
        </button>
      </span>
    );
  }
  if (!open) {
    return (
      <button type="button" className="button--secondary session__open" onClick={() => setOpen(true)}>
        Sign in to approve
      </button>
    );
  }
  return (
    <form className="session session__form" onSubmit={(event) => void signIn(event)}>
      <label htmlFor="approver-passphrase" className="visually-hidden">
        Approver passphrase
      </label>
      <input
        id="approver-passphrase"
        type="password"
        autoComplete="current-password"
        placeholder="Approver passphrase"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        autoFocus
      />
      <button type="submit" disabled={busy || password === ""}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <button type="button" className="link" onClick={() => setOpen(false)}>
        Cancel
      </button>
      {error && (
        <span role="alert" className="text-bad">
          {error}
        </span>
      )}
    </form>
  );
}
