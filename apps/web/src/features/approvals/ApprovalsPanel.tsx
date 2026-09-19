import { useEffect, useState } from "react";
import type { ApprovalSummary, Workspace } from "@ichnos/api-client";

import { api } from "../../api";
import { UNREACHABLE } from "../../labels";
import { StatusBadge } from "../runs/StatusBadge";
import { ApprovalReview } from "./ApprovalReview";
import { ACTION_LABEL } from "./payload";

type Props = {
  workspace: Workspace;
  approvalId?: string | undefined;
  onOpenApproval: (approvalId: string) => void;
  onCloseApproval: () => void;
};

export function ApprovalsPanel({ workspace, approvalId, onOpenApproval, onCloseApproval }: Props) {
  const [approvals, setApprovals] = useState<ApprovalSummary[] | null>(null);
  const [waitingOnly, setWaitingOnly] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (approvalId) return;
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.GET("/api/workspaces/{workspace_id}/approvals", {
          params: {
            path: { workspace_id: workspace.id },
            query: waitingOnly ? { status: "pending" } : {},
          },
        });
        if (!cancelled) setApprovals(data ?? []);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspace.id, approvalId, waitingOnly]);

  if (approvalId) return <ApprovalReview approvalId={approvalId} onBack={onCloseApproval} />;

  return (
    <section aria-labelledby="approvals-title">
      <h1 id="approvals-title">Approvals</h1>
      <p className="lede">
        Nothing reaches {workspace.repository} until a signed-in approver confirms the exact change.
      </p>
      <div className="filters" role="group" aria-label="Show">
        <button type="button" className="filters__button" aria-pressed={waitingOnly} onClick={() => setWaitingOnly(true)}>
          Waiting for you
        </button>
        <button type="button" className="filters__button" aria-pressed={!waitingOnly} onClick={() => setWaitingOnly(false)}>
          All
        </button>
      </div>
      {failed && <p className="notice notice--bad">{UNREACHABLE}</p>}
      {!failed && approvals === null && <p className="hint">Loading approvals…</p>}
      {approvals?.length === 0 && (
        <p className="empty">
          {waitingOnly ? "Nothing is waiting for approval." : "No actions have been proposed yet."}
        </p>
      )}
      {approvals && approvals.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Action</th>
                <th scope="col">Type</th>
                <th scope="col">Status</th>
                <th scope="col">Proposed by</th>
                <th scope="col">Proposed</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => (
                <tr key={approval.id}>
                  <td>
                    <button type="button" className="link" onClick={() => onOpenApproval(approval.id)}>
                      {approval.summary ?? approval.action_type}
                    </button>
                  </td>
                  <td>{ACTION_LABEL[approval.action_type] ?? approval.action_type}</td>
                  <td>
                    <StatusBadge status={approval.status} />
                  </td>
                  <td className="path">{approval.proposed_by}</td>
                  <td>{new Date(approval.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
