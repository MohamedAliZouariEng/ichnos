"""Minimal read-only GitHub REST client (ADR-0004)."""

from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr

from ichnos import __version__

GITHUB_API = "https://api.github.com"


class GitHubAccess(BaseModel):
    token_configured: bool
    repository_accessible: bool
    branch_exists: bool
    default_branch: str | None = None
    private: bool | None = None
    message: str


class GitHubClient:
    def __init__(
        self,
        token: SecretStr | None,
        *,
        base_url: str = GITHUB_API,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._transport = transport
        self._timeout = timeout

    @property
    def token_configured(self) -> bool:
        return self._token is not None and bool(self._token.get_secret_value())

    def _client(self) -> httpx.Client:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"ichnos/{__version__}",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token.get_secret_value()}"
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )

    def check_access(self, owner: str, repo: str, branch: str) -> GitHubAccess:
        """Check that the token can read the repository and that the branch exists."""
        if not self.token_configured:
            return GitHubAccess(
                token_configured=False,
                repository_accessible=False,
                branch_exists=False,
                message="No GitHub token configured; set ICHNOS_GITHUB_TOKEN in .env.",
            )
        try:
            with self._client() as client:
                repo_response = client.get(f"/repos/{owner}/{repo}")
                if repo_response.status_code != 200:
                    return self._failure(repo_response.status_code)
                data = repo_response.json()
                branch_path = f"/repos/{owner}/{repo}/branches/{quote(branch, safe='')}"
                branch_response = client.get(branch_path)
        except httpx.HTTPError:
            return GitHubAccess(
                token_configured=True,
                repository_accessible=False,
                branch_exists=False,
                message="Could not reach GitHub. Check the network connection.",
            )
        branch_exists = branch_response.status_code == 200
        return GitHubAccess(
            token_configured=True,
            repository_accessible=True,
            branch_exists=branch_exists,
            default_branch=data.get("default_branch"),
            private=data.get("private"),
            message=(
                "Repository and branch are accessible."
                if branch_exists
                else f"Repository is accessible, but branch '{branch}' was not found."
            ),
        )

    @staticmethod
    def _failure(status_code: int) -> GitHubAccess:
        messages = {
            401: "GitHub rejected the token. It may be expired or revoked.",
            403: "GitHub refused the request: missing permission or rate limit reached.",
            404: "Repository not found, or the token has no access to it.",
        }
        return GitHubAccess(
            token_configured=True,
            repository_accessible=False,
            branch_exists=False,
            message=messages.get(status_code, f"GitHub returned HTTP {status_code}."),
        )
