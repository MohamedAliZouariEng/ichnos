import { useState } from "react";
import type { ApprovalDetail } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE, detailOf } from "../../labels";
import type { IssuesPayload } from "./payload";

type Props = {
  approval: ApprovalDetail;
  payload: IssuesPayload;
  onSaved: (approval: ApprovalDetail) => void;
  onCancel: () => void;
};

/** Edit titles and bodies of a pending plan; saving changes the hash that gets approved. */
export function IssuesEditor({ approval, payload, onSaved, onCancel }: Props) {
  const [epic, setEpic] = useState({ title: payload.epic.title, body: payload.epic.body });
  const [stories, setStories] = useState(
    payload.stories.map((story) => ({ key: story.key ?? "", title: story.title, body: story.body })),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setStory(index: number, field: "title" | "body", value: string) {
    setStories((current) => current.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const { data, error: failure } = await api.POST("/api/approvals/{approval_id}/revise", {
        params: { path: { approval_id: approval.id } },
        body: { payload_hash: approval.payload_hash, epic, stories },
      });
      if (data) onSaved(data);
      else setError(detailOf(failure) ?? "The changes could not be saved.");
    } catch {
      setError(UNREACHABLE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-label="Edit Issues">
      <h2>Edit Issues</h2>
      <p className="hint">
        Keep each Story's <code>## Parent</code> line. Saving changes the payload hash, so you then
        approve the edited text.
      </p>
      <div className="field">
        <label htmlFor="epic-title">Epic title</label>
        <input id="epic-title" value={epic.title} onChange={(e) => setEpic({ ...epic, title: e.target.value })} />
        <label htmlFor="epic-body">Epic body</label>
        <textarea id="epic-body" rows={8} value={epic.body} onChange={(e) => setEpic({ ...epic, body: e.target.value })} />
      </div>
      {stories.map((story, index) => (
        <div className="field" key={story.key}>
          <label htmlFor={`${story.key}-title`}>{story.key} title</label>
          <input
            id={`${story.key}-title`}
            value={story.title}
            onChange={(e) => setStory(index, "title", e.target.value)}
          />
          <label htmlFor={`${story.key}-body`}>{story.key} body</label>
          <textarea
            id={`${story.key}-body`}
            rows={8}
            value={story.body}
            onChange={(e) => setStory(index, "body", e.target.value)}
          />
        </div>
      ))}
      <div className="actions">
        <button type="button" onClick={() => void save()} disabled={busy}>
          {busy ? "Saving…" : "Save changes"}
        </button>
        <button type="button" className="button--secondary" onClick={onCancel}>
          Cancel
        </button>
        {error && (
          <span role="alert" className="text-bad">
            {error}
          </span>
        )}
      </div>
    </section>
  );
}
