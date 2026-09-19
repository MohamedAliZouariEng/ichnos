import { type FormEvent, useEffect, useState } from "react";
import type { GitHubAccess, ServerConfig, Workspace, WorkspaceCreate } from "@ichnos/api-client";

import { api } from "../../api";
import { ModelNotice } from "../../components/ModelNotice";

type FormState = {
  name: string;
  repository: string;
  branch: string;
  indexPaths: string;
  llmProvider: string;
  llmModel: string;
  embeddingProvider: string;
  embeddingModel: string;
};
type FieldName = keyof FormState;
type FieldErrors = Partial<Record<FieldName, string>>;
type SaveStatus =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

const EMPTY_FORM: FormState = {
  name: "",
  repository: "",
  branch: "main",
  indexPaths: "docs/\n.github/",
  llmProvider: "",
  llmModel: "",
  embeddingProvider: "",
  embeddingModel: "",
};

const API_FIELDS: Record<string, FieldName> = {
  name: "name",
  repository: "repository",
  branch: "branch",
  index_paths: "indexPaths",
  llm_provider: "llmProvider",
  llm_model: "llmModel",
  embedding_provider: "embeddingProvider",
  embedding_model: "embeddingModel",
};

const FIELD_HINTS: Partial<Record<FieldName, string>> = {
  name: "Enter a name of up to 100 characters.",
  repository: "Use the form owner/name, for example octo-org/demo.",
  indexPaths: "Use paths relative to the repository root, like docs/.",
};

const UNREACHABLE = "Could not reach the API. Check that it is running, then try again.";

function fromWorkspace(workspace: Workspace): FormState {
  return {
    name: workspace.name,
    repository: workspace.repository,
    branch: workspace.branch ?? "main",
    indexPaths: (workspace.index_paths ?? []).join("\n"),
    llmProvider: workspace.llm_provider ?? "",
    llmModel: workspace.llm_model ?? "",
    embeddingProvider: workspace.embedding_provider ?? "",
    embeddingModel: workspace.embedding_model ?? "",
  };
}

const optional = (value: string) => value.trim() || null;

function toBody(form: FormState): WorkspaceCreate {
  return {
    name: form.name.trim(),
    repository: form.repository.trim(),
    branch: form.branch.trim() || "main",
    index_paths: form.indexPaths
      .split("\n")
      .map((path) => path.trim())
      .filter(Boolean),
    llm_provider: optional(form.llmProvider),
    llm_model: optional(form.llmModel),
    embedding_provider: optional(form.embeddingProvider),
    embedding_model: optional(form.embeddingModel),
  };
}

function detailOf(error: unknown): unknown {
  return typeof error === "object" && error !== null && "detail" in error
    ? (error as { detail: unknown }).detail
    : undefined;
}

function fieldErrorsFrom(error: unknown): FieldErrors {
  const detail = detailOf(error);
  const errors: FieldErrors = {};
  if (!Array.isArray(detail)) return errors;
  for (const item of detail as Array<{ loc?: unknown[]; msg?: string }>) {
    const field = API_FIELDS[String(item.loc?.[1] ?? "")];
    if (field && !errors[field]) errors[field] = FIELD_HINTS[field] ?? item.msg ?? "Invalid value.";
  }
  return errors;
}

function messageFrom(error: unknown): string {
  const detail = detailOf(error);
  return typeof detail === "string" ? detail : "Some fields need attention.";
}

type FieldProps = {
  id: FieldName;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string | undefined;
  hint?: string;
  placeholder?: string;
  multiline?: boolean;
};

function Field({ id, label, value, onChange, error, hint, placeholder, multiline }: FieldProps) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ");
  const common = {
    id,
    value,
    placeholder,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy || undefined,
  };
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea rows={3} {...common} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input type="text" {...common} onChange={(event) => onChange(event.target.value)} />
      )}
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="field__error">
          {error}
        </p>
      )}
    </div>
  );
}

type WorkspacePanelProps = {
  /** undefined: the first workspace; null: a new one; a string: that workspace. */
  workspaceId?: string | null | undefined;
  onSaved?: (workspace: Workspace) => void;
};

export function WorkspacePanel({ workspaceId, onSaved }: WorkspacePanelProps = {}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [status, setStatus] = useState<SaveStatus>({ kind: "idle" });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [access, setAccess] = useState<GitHubAccess | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [workspaces, serverConfig] = await Promise.all([
          api.GET("/api/workspaces"),
          api.GET("/api/config"),
        ]);
        if (cancelled) return;
        const all = workspaces.data ?? [];
        const first =
          workspaceId === undefined
            ? (all[0] ?? null)
            : (all.find((w) => w.id === workspaceId) ?? null);
        setWorkspace(first);
        setForm(first ? fromWorkspace(first) : EMPTY_FORM);
        setConfig(serverConfig.data ?? null);
      } catch {
        if (!cancelled) setLoadFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  function update(field: FieldName, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setStatus({ kind: "idle" });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus({ kind: "saving" });
    setFieldErrors({});
    const body = toBody(form);
    try {
      const result = workspace
        ? await api.PATCH("/api/workspaces/{workspace_id}", {
            params: { path: { workspace_id: workspace.id } },
            body,
          })
        : await api.POST("/api/workspaces", { body });
      if (result.data) {
        setWorkspace(result.data);
        setForm(fromWorkspace(result.data));
        setAccess(null);
        setStatus({ kind: "saved" });
        onSaved?.(result.data);
        return;
      }
      setFieldErrors(fieldErrorsFrom(result.error));
      setStatus({ kind: "error", message: messageFrom(result.error) });
    } catch {
      setStatus({ kind: "error", message: UNREACHABLE });
    }
  }

  async function checkGitHub() {
    if (!workspace) return;
    setChecking(true);
    try {
      const { data } = await api.POST("/api/workspaces/{workspace_id}/github-check", {
        params: { path: { workspace_id: workspace.id } },
      });
      setAccess(data ?? null);
    } catch {
      setAccess({
        token_configured: config?.github_token_configured ?? false,
        repository_accessible: false,
        branch_exists: false,
        message: UNREACHABLE,
      });
    } finally {
      setChecking(false);
    }
  }

  if (loading) return <p className="lede">Loading workspace…</p>;

  if (loadFailed) {
    return (
      <section aria-labelledby="workspace-title">
        <h1 id="workspace-title">Workspace</h1>
        <p className="notice notice--bad">{UNREACHABLE}</p>
      </section>
    );
  }

  const tokenConfigured = config?.github_token_configured ?? false;
  const accessOk = Boolean(access?.repository_accessible && access.branch_exists);

  return (
    <section aria-labelledby="workspace-title">
      <h1 id="workspace-title">Workspace</h1>
      <p className="lede">
        {workspace
          ? "The GitHub repository Ichnos reads for this workspace."
          : "Connect the GitHub repository Ichnos should read."}
      </p>

      <form className="panel" onSubmit={(event) => void save(event)} noValidate>
        <h2>Repository</h2>
        <Field
          id="name"
          label="Name"
          value={form.name}
          onChange={(value) => update("name", value)}
          error={fieldErrors.name}
          placeholder="ichnos"
        />
        <Field
          id="repository"
          label="Repository"
          value={form.repository}
          onChange={(value) => update("repository", value)}
          error={fieldErrors.repository}
          hint="owner/name on GitHub"
          placeholder="octo-org/demo"
        />
        <Field
          id="branch"
          label="Branch"
          value={form.branch}
          onChange={(value) => update("branch", value)}
          error={fieldErrors.branch}
        />
        <Field
          id="indexPaths"
          label="Paths to index"
          value={form.indexPaths}
          onChange={(value) => update("indexPaths", value)}
          error={fieldErrors.indexPaths}
          hint="One path per line, relative to the repository root."
          multiline
        />

        <fieldset className="fieldset">
          <legend>Models</legend>
          <p className="hint">
            Optional. Leave empty to use the server’s model for this workspace.
          </p>
          <ModelNotice config={config} />
          <div className="fieldset__grid">
            <Field
              id="llmProvider"
              label="LLM provider"
              value={form.llmProvider}
              onChange={(value) => update("llmProvider", value)}
              error={fieldErrors.llmProvider}
              placeholder={config?.llm_provider ?? "not set"}
            />
            <Field
              id="llmModel"
              label="LLM model"
              value={form.llmModel}
              onChange={(value) => update("llmModel", value)}
              error={fieldErrors.llmModel}
              placeholder={config?.llm_model ?? "not set"}
            />
            <Field
              id="embeddingProvider"
              label="Embedding provider"
              value={form.embeddingProvider}
              onChange={(value) => update("embeddingProvider", value)}
              error={fieldErrors.embeddingProvider}
              placeholder={config?.embedding_provider ?? "not set"}
            />
            <Field
              id="embeddingModel"
              label="Embedding model"
              value={form.embeddingModel}
              onChange={(value) => update("embeddingModel", value)}
              error={fieldErrors.embeddingModel}
              placeholder={config?.embedding_model ?? "not set"}
            />
          </div>
        </fieldset>

        <div className="actions">
          <button type="submit" disabled={status.kind === "saving"}>
            {status.kind === "saving" ? "Saving…" : "Save workspace"}
          </button>
          <p
            role="status"
            className={status.kind === "error" ? "save-status save-status--error" : "save-status"}
          >
            {status.kind === "saved" && "Workspace saved."}
            {status.kind === "error" && status.message}
          </p>
        </div>
      </form>

      <section className="panel" aria-labelledby="github-title">
        <h2 id="github-title">GitHub access</h2>
        <p>
          Token: <strong>{tokenConfigured ? "configured" : "not configured"}</strong>
        </p>
        {!tokenConfigured && (
          <p className="hint">
            Add ICHNOS_GITHUB_TOKEN to .env, then restart the API. Read access is enough for now.
          </p>
        )}
        <div className="actions">
          <button
            type="button"
            className="button--secondary"
            onClick={() => void checkGitHub()}
            disabled={!workspace || checking}
          >
            {checking ? "Checking…" : "Check GitHub access"}
          </button>
          {!workspace && <p className="hint">Save the workspace first.</p>}
        </div>
        {access && (
          <p className={accessOk ? "notice notice--ok" : "notice notice--bad"} role="status">
            {access.message}
            {access.default_branch && ` Default branch: ${access.default_branch}.`}
          </p>
        )}
      </section>
    </section>
  );
}
