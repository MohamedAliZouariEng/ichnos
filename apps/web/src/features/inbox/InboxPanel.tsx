import { useState } from "react";
import type { Workspace } from "@ichnos/api-client";

import { DocumentDetailView } from "./DocumentDetailView";
import { DocumentList } from "./DocumentList";
import { SearchBox } from "./SearchBox";
import { SyncBar } from "./SyncBar";

type Props = {
  workspace: Workspace;
  documentPath?: string | undefined;
  onOpenDocument: (path: string) => void;
  onCloseDocument: () => void;
};

export function InboxPanel({ workspace, documentPath, onOpenDocument, onCloseDocument }: Props) {
  const [refreshKey, setRefreshKey] = useState(0);

  if (documentPath) {
    return (
      <DocumentDetailView
        workspaceId={workspace.id}
        path={documentPath}
        onOpenDocument={onOpenDocument}
        onBack={onCloseDocument}
      />
    );
  }
  return (
    <section aria-labelledby="inbox-title">
      <h1 id="inbox-title">Inbox</h1>
      <p className="lede">
        Documents synced from <span className="path">{workspace.repository}</span> on{" "}
        <span className="path">{workspace.branch}</span>.
      </p>
      <SyncBar workspaceId={workspace.id} onSynced={() => setRefreshKey((key) => key + 1)} />
      <SearchBox workspaceId={workspace.id} onOpenDocument={onOpenDocument} />
      <DocumentList workspaceId={workspace.id} refreshKey={refreshKey} onOpen={onOpenDocument} />
    </section>
  );
}
