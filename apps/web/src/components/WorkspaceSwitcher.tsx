import type { Workspace } from "@ichnos/api-client";

const NEW = "__new__";

type Props = {
  workspaces: Workspace[];
  selectedId: string | null;
  creating: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
};

export function WorkspaceSwitcher({ workspaces, selectedId, creating, onSelect, onCreate }: Props) {
  if (workspaces.length === 0) return null;
  return (
    <label className="switcher">
      <span className="switcher__label">Workspace</span>
      <select
        value={creating ? NEW : (selectedId ?? "")}
        onChange={(event) =>
          event.target.value === NEW ? onCreate() : onSelect(event.target.value)
        }
      >
        {workspaces.map((workspace) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.name} · {workspace.repository}
          </option>
        ))}
        <option value={NEW}>New workspace…</option>
      </select>
    </label>
  );
}
