import { useState } from "react";

import { HealthBadge } from "./components/HealthBadge";
import { SessionControl } from "./components/SessionControl";
import { WorkspaceSwitcher } from "./components/WorkspaceSwitcher";
import { GitHubPanel } from "./features/github/GitHubPanel";
import { ApprovalsPanel } from "./features/approvals/ApprovalsPanel";
import { ArtifactsPanel } from "./features/artifacts/ArtifactsPanel";
import { InboxPanel } from "./features/inbox/InboxPanel";
import { RunsPanel } from "./features/runs/RunsPanel";
import { WorkspacePanel } from "./features/workspace/WorkspacePanel";
import { type Section, useRoute } from "./route";
import { useWorkspaces } from "./workspaces";

const CURRENT_PHASE = 4;

// Ordered the way work flows through Ichnos; each section names the phase that delivers it.
const SECTIONS: { id: string; section?: Section; label: string; phase: number }[] = [
  { id: "workspace", section: "workspace", label: "Workspace", phase: 1 },
  { id: "inbox", section: "inbox", label: "Inbox", phase: 2 },
  { id: "github", section: "github", label: "GitHub context", phase: 2 },
  { id: "runs", section: "runs", label: "Workflow runs", phase: 3 },
  { id: "artifacts", section: "artifacts", label: "Artifacts", phase: 3 },
  { id: "approvals", section: "approvals", label: "Approvals", phase: 4 },
  { id: "traceability", label: "Traceability", phase: 6 },
];

export function App() {
  const [route, navigate] = useRoute();
  const { workspaces, selected, select, refresh } = useWorkspaces();
  const [creating, setCreating] = useState(false);
  const section: Section = creating || !selected ? "workspace" : route.section;

  function open(next: Section) {
    setCreating(false);
    navigate({ section: next });
  }

  function content() {
    if (section === "inbox" && selected) {
      return (
        <InboxPanel
          key={selected.id}
          workspace={selected}
          documentPath={route.doc}
          onOpenDocument={(path) => navigate({ section: "inbox", doc: path })}
          onCloseDocument={() => navigate({ section: "inbox" })}
        />
      );
    }
    if (section === "approvals" && selected) {
      return (
        <ApprovalsPanel
          key={selected.id}
          workspace={selected}
          approvalId={route.approval}
          onOpenApproval={(id) => navigate({ section: "approvals", approval: id })}
          onCloseApproval={() => navigate({ section: "approvals" })}
        />
      );
    }
    if (section === "artifacts" && selected) {
      return (
        <ArtifactsPanel
          key={selected.id}
          workspace={selected}
          artifactId={route.artifact}
          onOpenArtifact={(id) => navigate({ section: "artifacts", artifact: id })}
          onCloseArtifact={() => navigate({ section: "artifacts" })}
        />
      );
    }
    if (section === "runs" && selected) {
      return (
        <RunsPanel
          key={selected.id}
          workspace={selected}
          runId={route.run}
          onOpenRun={(id) => navigate({ section: "runs", run: id })}
          onCloseRun={() => navigate({ section: "runs" })}
          onOpenArtifact={(id) => navigate({ section: "artifacts", artifact: id })}
        />
      );
    }
    if (section === "github" && selected) {
      return (
        <GitHubPanel
          key={selected.id}
          workspace={selected}
          onOpenDocument={(path) => navigate({ section: "inbox", doc: path })}
        />
      );
    }
    return (
      <WorkspacePanel
        key={creating ? "new" : (selected?.id ?? "first")}
        workspaceId={creating ? null : selected?.id}
        onSaved={(workspace) => {
          setCreating(false);
          void refresh().then(() => select(workspace.id));
        }}
      />
    );
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <p className="wordmark">ichnos</p>
        <nav aria-label="Main">
          <ol className="trace">
            {SECTIONS.map((item) => {
              const available = item.phase <= CURRENT_PHASE && item.section !== undefined;
              const current = item.section === section;
              const classes = ["trace__step"];
              if (available) classes.push("trace__step--available");
              if (current) classes.push("trace__step--current");
              return (
                <li key={item.id} className={classes.join(" ")}>
                  <span className="trace__node" aria-hidden="true" />
                  {available && item.section ? (
                    <button
                      type="button"
                      className="trace__link"
                      aria-current={current ? "page" : undefined}
                      onClick={() => open(item.section as Section)}
                    >
                      {item.label}
                    </button>
                  ) : (
                    <span className="trace__label">{item.label}</span>
                  )}
                  {!available && <span className="trace__phase">Phase {item.phase}</span>}
                </li>
              );
            })}
          </ol>
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <WorkspaceSwitcher
            workspaces={workspaces}
            selectedId={selected?.id ?? null}
            creating={creating}
            onSelect={(id) => {
              setCreating(false);
              select(id);
            }}
            onCreate={() => setCreating(true)}
          />
          <div className="topbar__right">
            <SessionControl />
            <HealthBadge />
          </div>
        </header>
        <main className="content">{content()}</main>
      </div>
    </div>
  );
}
