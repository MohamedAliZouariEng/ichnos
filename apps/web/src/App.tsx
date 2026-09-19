import { HealthBadge } from "./components/HealthBadge";
import { WorkspacePanel } from "./features/workspace/WorkspacePanel";

const CURRENT_PHASE = 1;

// Ordered the way work flows through Ichnos; each section names the phase that delivers it.
const SECTIONS = [
  { id: "workspace", label: "Workspace", phase: 1 },
  { id: "inbox", label: "Inbox", phase: 2 },
  { id: "runs", label: "Workflow runs", phase: 3 },
  { id: "artifacts", label: "Artifacts", phase: 3 },
  { id: "approvals", label: "Approvals", phase: 4 },
  { id: "traceability", label: "Traceability", phase: 6 },
] as const;

export function App() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <p className="wordmark">ichnos</p>
        <nav aria-label="Main">
          <ol className="trace">
            {SECTIONS.map((section) => {
              const available = section.phase <= CURRENT_PHASE;
              return (
                <li
                  key={section.id}
                  className={available ? "trace__step trace__step--current" : "trace__step"}
                  aria-current={section.id === "workspace" ? "page" : undefined}
                >
                  <span className="trace__node" aria-hidden="true" />
                  <span className="trace__label">{section.label}</span>
                  {!available && <span className="trace__phase">Phase {section.phase}</span>}
                </li>
              );
            })}
          </ol>
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <HealthBadge />
        </header>
        <main className="content">
          <WorkspacePanel />
        </main>
      </div>
    </div>
  );
}
