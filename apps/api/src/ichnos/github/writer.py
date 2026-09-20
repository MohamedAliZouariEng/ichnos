"""The only GitHub client that writes (ADR-0015, ADR-0017).

It is built from an execution ticket, which only the approval service issues. Documentation is
committed atomically on a new branch through the Git Data API; the default branch is never
written to, and nothing is ever merged.
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from ichnos.approvals.ticket import ExecutionTicket

GITHUB_API = "https://api.github.com"
FILE_MODE = "100644"


class GitHubWriteError(Exception):
    """GitHub refused or could not receive a write; the message is safe to show."""


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str


@dataclass(frozen=True)
class Created:
    number: int
    url: str


class GitHubWriter:
    def __init__(
        self,
        ticket: ExecutionTicket,
        *,
        repository: str,
        token: SecretStr,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not isinstance(ticket, ExecutionTicket):
            raise PermissionError(
                "GitHub writes need an execution ticket from the approval service (ADR-0015)."
            )
        owner, _, name = repository.partition("/")
        if not owner or not name:
            raise ValueError(f"Not an owner/name repository: {repository!r}")
        self.ticket = ticket
        self._prefix = f"/repos/{owner}/{name}"
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                # Every write names the approval that allowed it (ADR-0015).
                "X-Ichnos-Approval": ticket.approval_id,
            },
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "GitHubWriter":
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._client.close()

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        params: dict[str, str] | None = None,
        allow_404: bool = False,
    ) -> Any:
        try:
            response = self._client.request(method, self._prefix + path, json=body, params=params)
        except httpx.HTTPError as exc:
            raise GitHubWriteError(f"Could not reach GitHub ({exc.__class__.__name__}).") from exc
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code >= 400:
            try:
                message = str(response.json().get("message", ""))
            except ValueError:
                message = ""
            detail = f": {message}" if message else ""
            raise GitHubWriteError(
                f"GitHub refused {method} {path} (HTTP {response.status_code}){detail}"
            )
        return response.json() if response.content else {}

    def branch_head(self, branch: str) -> str | None:
        ref = self._call("GET", f"/git/ref/heads/{quote(branch, safe='/')}", allow_404=True)
        return None if ref is None else str(ref["object"]["sha"])

    def file_sha(self, path: str, ref: str) -> str | None:
        """Blob SHA of a file on a branch, or None when it does not exist."""
        data = self._call(
            "GET", f"/contents/{quote(path, safe='/')}", params={"ref": ref}, allow_404=True
        )
        return None if data is None or isinstance(data, list) else str(data["sha"])

    def commit_files(
        self, *, base_branch: str, new_branch: str, message: str, files: list[FileChange]
    ) -> str:
        """One commit with every file, on a new branch from base_branch; the ref comes last."""
        base_sha = self.branch_head(base_branch)
        if base_sha is None:
            raise GitHubWriteError(f"Branch {base_branch} does not exist.")
        base_commit = self._call("GET", f"/git/commits/{base_sha}")
        entries = []
        for change in files:
            blob = self._call(
                "POST", "/git/blobs", {"content": change.content, "encoding": "utf-8"}
            )
            entries.append(
                {"path": change.path, "mode": FILE_MODE, "type": "blob", "sha": blob["sha"]}
            )
        tree = self._call(
            "POST", "/git/trees", {"base_tree": base_commit["tree"]["sha"], "tree": entries}
        )
        commit = self._call(
            "POST", "/git/commits", {"message": message, "tree": tree["sha"], "parents": [base_sha]}
        )
        self._call("POST", "/git/refs", {"ref": f"refs/heads/{new_branch}", "sha": commit["sha"]})
        return str(commit["sha"])

    def start_branch(self, *, base_branch: str, new_branch: str, message: str) -> str:
        """A new branch whose only commit changes nothing: its tree is the base tree (ADR-0021)."""
        base_sha = self.branch_head(base_branch)
        if base_sha is None:
            raise GitHubWriteError(f"Branch {base_branch} does not exist.")
        tree = self._call("GET", f"/git/commits/{base_sha}")["tree"]["sha"]
        commit = self._call(
            "POST", "/git/commits", {"message": message, "tree": tree, "parents": [base_sha]}
        )
        written = self._call("GET", f"/git/commits/{commit['sha']}")
        if written["tree"]["sha"] != tree:
            raise GitHubWriteError("The first commit would change files; no branch was created.")
        self._call("POST", "/git/refs", {"ref": f"refs/heads/{new_branch}", "sha": commit["sha"]})
        return str(commit["sha"])

    def open_pull_request(
        self, *, head: str, base: str, title: str, body: str, draft: bool = False
    ) -> Created:
        data = self._call(
            "POST",
            "/pulls",
            {"head": head, "base": base, "title": title, "body": body, "draft": draft},
        )
        return Created(int(data["number"]), str(data["html_url"]))

    def ensure_labels(self, labels: dict[str, str]) -> None:
        """Create any missing label; colours are six hex digits without #."""
        for name, color in labels.items():
            if self._call("GET", f"/labels/{quote(name, safe='')}", allow_404=True) is None:
                self._call("POST", "/labels", {"name": name, "color": color})

    def create_issue(self, *, title: str, body: str, labels: list[str]) -> Created:
        data = self._call("POST", "/issues", {"title": title, "body": body, "labels": labels})
        return Created(int(data["number"]), str(data["html_url"]))
