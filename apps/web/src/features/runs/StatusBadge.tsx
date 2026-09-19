const TONES: Record<string, string> = {
  queued: "info",
  running: "info",
  succeeded: "ok",
  failed: "bad",
  interrupted: "warn",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge--${TONES[status] ?? "muted"}`}>{status}</span>;
}
