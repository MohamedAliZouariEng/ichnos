import { useCallback, useEffect, useRef, useState } from "react";

const SEEN = "ichnos.quick-tips.seen";

type Tip = { title: string; text: string };

export const TIPS: Tip[] = [
  {
    title: "Welcome to Ichnos",
    text: "Ichnos reads your repository's notes, Issues and code, helps you write requirements and plans, and asks you before it writes anything back.",
  },
  {
    title: "Workspace",
    text: "Point Ichnos at one GitHub repository, then sync it. Everything else works from what it finds there.",
  },
  {
    title: "Inbox",
    text: "The documents it synced: meeting notes, requirements and decisions, each with who verified it.",
  },
  {
    title: "GitHub context",
    text: "Your Issues and pull requests. Open a Story here to see everything needed to build it.",
  },
  {
    title: "Workflow runs",
    text: "Where you ask Ichnos to draft something, such as requirements from a meeting note, and watch it work.",
  },
  {
    title: "Artifacts",
    text: "Drafts you can read, edit and version before anyone else sees them. Nothing here has left Ichnos yet.",
  },
  {
    title: "Approvals",
    text: "Every change to GitHub waits here. You see the exact files, then approve or reject. Ichnos never writes on its own.",
  },
  {
    title: "Traceability",
    text: "Each requirement followed to its Stories, pull requests and tests, with what is missing shown plainly.",
  },
  {
    title: "Questions",
    text: "Ask about your project. Every sentence of the answer links to its source, and gaps are listed as gaps.",
  },
  {
    title: "That's it",
    text: "Start in Workspace and sync. You can open these tips again from Quick tips at the top of the page.",
  },
];

function remember(): void {
  try {
    window.localStorage.setItem(SEEN, "1");
  } catch {
    // Private browsing: the tips simply appear again next time.
  }
}

export function seenQuickTips(): boolean {
  try {
    return window.localStorage.getItem(SEEN) === "1";
  } catch {
    return false;
  }
}

/** A very simple introduction: one short card at a time, in the order you use the app. */
export function QuickTips({ onClose }: { onClose: () => void }) {
  const [at, setAt] = useState(0);
  const dialog = useRef<HTMLDivElement>(null);
  const tip = TIPS[at];
  const last = at === TIPS.length - 1;

  const close = useCallback(() => {
    remember();
    onClose();
  }, [onClose]);

  useEffect(() => {
    dialog.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight") setAt((n) => Math.min(n + 1, TIPS.length - 1));
      if (event.key === "ArrowLeft") setAt((n) => Math.max(n - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  if (!tip) return null;
  return (
    <div className="overlay" onClick={close}>
      <div
        className="overlay__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-tips-title"
        tabIndex={-1}
        ref={dialog}
        onClick={(event) => event.stopPropagation()}
      >
        <p className="hint">
          Quick tips · {at + 1} of {TIPS.length}
        </p>
        <h2 id="quick-tips-title">{tip.title}</h2>
        <p>{tip.text}</p>
        <div className="overlay__actions">
          <button type="button" className="button--secondary" onClick={close}>
            {last ? "Close" : "Skip"}
          </button>
          <span className="overlay__spacer" />
          {at > 0 && (
            <button type="button" className="button--secondary" onClick={() => setAt(at - 1)}>
              Back
            </button>
          )}
          <button type="button" onClick={() => (last ? close() : setAt(at + 1))}>
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
