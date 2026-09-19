"""Read-only GitHub REST access for sync (ADR-0009): pagination, ETags and rate limits."""

import base64
import datetime as dt
from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from ichnos import __version__
from ichnos.github.client import GITHUB_API

PER_PAGE = 100
Params = Mapping[str, str | int]


class GitHubError(Exception):
    """GitHub answered with an error status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class RateLimitExceeded(GitHubError):
    """The rate limit is used up; retry after reset_at."""

    def __init__(self, status_code: int, reset_at: dt.datetime | None) -> None:
        when = reset_at.isoformat() if reset_at else "the limit resets"
        super().__init__(status_code, f"Rate limit reached; try again after {when}.")
        self.reset_at = reset_at


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int | None


def _reset_time(response: httpx.Response) -> dt.datetime | None:
    retry_after = response.headers.get("Retry-After", "")
    if retry_after.isdigit():
        return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=int(retry_after))
    reset = response.headers.get("X-RateLimit-Reset", "")
    if reset.isdigit():
        return dt.datetime.fromtimestamp(int(reset), dt.UTC)
    return None


class GitHubReader:
    """One HTTP session per sync run. Use it as a context manager."""

    def __init__(
        self,
        token: SecretStr | None,
        *,
        base_url: str = GITHUB_API,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        etags: MutableMapping[str, str] | None = None,
        max_pages: int = 50,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"ichnos/{__version__}",
        }
        if token is not None and token.get_secret_value():
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        self._client = httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        )
        self._etags: MutableMapping[str, str] = etags if etags is not None else {}
        self._max_pages = max_pages
        self.requests = 0
        self.rate_limit_remaining: int | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---- transport ----

    def _request(
        self, url: str, params: Params | None = None, *, conditional: bool = False
    ) -> httpx.Response | None:
        """GET a URL. Returns None when a conditional request reports no change (304)."""
        key = str(self._client.build_request("GET", url, params=params).url)
        headers = {}
        if conditional and key in self._etags:
            headers["If-None-Match"] = self._etags[key]
        response = self._client.get(url, params=params, headers=headers)
        self.requests += 1
        remaining = response.headers.get("X-RateLimit-Remaining", "")
        if remaining.isdigit():
            self.rate_limit_remaining = int(remaining)
        if response.status_code == 304:
            return None
        self._raise_for_status(response)
        etag = response.headers.get("ETag")
        if conditional and etag:
            self._etags[key] = etag
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        remaining = response.headers.get("X-RateLimit-Remaining")
        limited = remaining == "0" or "Retry-After" in response.headers
        if status == 429 or (status == 403 and limited):
            raise RateLimitExceeded(status, _reset_time(response))
        message = response.reason_phrase
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("message"):
            message = str(body["message"])
        raise GitHubError(status, message)

    def get_json(self, url: str, params: Params | None = None, *, conditional: bool = False) -> Any:
        response = self._request(url, params, conditional=conditional)
        return None if response is None else response.json()

    def paginate(
        self, url: str, params: Params | None = None, *, conditional: bool = False
    ) -> Iterator[dict[str, Any]]:
        """Yield every item of a list endpoint, following Link headers."""
        next_url = url
        next_params: Params | None = {"per_page": PER_PAGE, **(params or {})}
        for page in range(self._max_pages):
            response = self._request(next_url, next_params, conditional=conditional and page == 0)
            if response is None:
                return
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubError(response.status_code, f"Expected a list from {url}.")
            yield from (item for item in payload if isinstance(item, dict))
            following = response.links.get("next", {}).get("url")
            if not following:
                return
            next_url, next_params = following, None
        raise GitHubError(0, f"Stopped after {self._max_pages} pages of {url}.")

    # ---- repository files ----

    @staticmethod
    def _repo(owner: str, repo: str) -> str:
        return f"/repos/{owner}/{repo}"

    def branch_head(self, owner: str, repo: str, branch: str) -> str:
        data = self.get_json(f"{self._repo(owner, repo)}/branches/{quote(branch, safe='')}")
        return str(data["commit"]["sha"])

    def tree(self, owner: str, repo: str, sha: str) -> list[TreeEntry]:
        data = self.get_json(f"{self._repo(owner, repo)}/git/trees/{sha}", {"recursive": 1})
        if data.get("truncated"):
            raise GitHubError(200, "The repository tree is too large to read in one request.")
        return [
            TreeEntry(path=entry["path"], sha=entry["sha"], size=entry.get("size"))
            for entry in data.get("tree", [])
            if entry.get("type") == "blob"
        ]

    def blob_text(self, owner: str, repo: str, sha: str) -> str:
        data = self.get_json(f"{self._repo(owner, repo)}/git/blobs/{sha}")
        content = str(data.get("content", ""))
        if data.get("encoding") != "base64":
            return content
        return base64.b64decode(content).decode("utf-8", errors="replace")

    # ---- history ----

    def _since(self, params: dict[str, str | int], since: str | None) -> dict[str, str | int]:
        if since:
            params["since"] = since
        return params

    def issues(self, owner: str, repo: str, since: str | None) -> Iterator[dict[str, Any]]:
        """Issues and pull requests, oldest update first."""
        params = self._since({"state": "all", "sort": "updated", "direction": "asc"}, since)
        return self.paginate(f"{self._repo(owner, repo)}/issues", params)

    def issue_comments(self, owner: str, repo: str, since: str | None) -> Iterator[dict[str, Any]]:
        params = self._since({"sort": "updated", "direction": "asc"}, since)
        return self.paginate(f"{self._repo(owner, repo)}/issues/comments", params)

    def commits(
        self, owner: str, repo: str, branch: str, since: str | None
    ) -> Iterator[dict[str, Any]]:
        params = self._since({"sha": branch}, since)
        return self.paginate(f"{self._repo(owner, repo)}/commits", params)

    def pull(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        data: dict[str, Any] = self.get_json(f"{self._repo(owner, repo)}/pulls/{number}")
        return data

    def pull_reviews(self, owner: str, repo: str, number: int) -> Iterator[dict[str, Any]]:
        return self.paginate(f"{self._repo(owner, repo)}/pulls/{number}/reviews")

    def pull_review_comments(self, owner: str, repo: str, number: int) -> Iterator[dict[str, Any]]:
        return self.paginate(f"{self._repo(owner, repo)}/pulls/{number}/comments")

    def pull_files(self, owner: str, repo: str, number: int) -> Iterator[dict[str, Any]]:
        return self.paginate(f"{self._repo(owner, repo)}/pulls/{number}/files")

    def pull_commits(self, owner: str, repo: str, number: int) -> Iterator[dict[str, Any]]:
        return self.paginate(f"{self._repo(owner, repo)}/pulls/{number}/commits")
