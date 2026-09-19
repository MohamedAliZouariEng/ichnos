import { useCallback, useEffect, useState } from "react";
import type { Workspace } from "@ichnos/api-client";

import { api } from "./api";

const STORAGE_KEY = "ichnos.workspace";

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** All workspaces and the selected one; the selection is remembered in this browser. */
export function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(readStored);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.GET("/api/workspaces");
      setWorkspaces(data ?? []);
    } catch {
      setWorkspaces([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // Storage can be unavailable (private mode); the selection then lasts for this visit.
    }
  }, []);

  const selected = workspaces.find((w) => w.id === selectedId) ?? workspaces[0] ?? null;
  return { workspaces, selected, select, refresh };
}
