"""Read files and branch heads from GitHub to build payloads (read-only; ADR-0015)."""

import base64
from dataclasses import dataclass
from types import TracebackType
from urllib.parse import quote

import httpx
from pydantic import SecretStr

GITHUB_API = "https://api.github.com"


class ContentsError(Exception):
    """GitHub could not be read; the message is safe to show."""


@dataclass(frozen=True)
class RepoFile:
    text: str
    sha: str


class ContentsReader:
    def __init__(
        self,
        repository: str,
        token: SecretStr,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._prefix = f"/repos/{repository}"
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            transport=transport,
        )

    def __enter__(self) -> "ContentsReader":
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response | None:
        try:
            response = self._client.get(self._prefix + path, params=params)
        except httpx.HTTPError as exc:
            raise ContentsError(f"Could not reach GitHub ({exc.__class__.__name__}).") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ContentsError(f"GitHub refused GET {path} (HTTP {response.status_code}).")
        return response

    def head(self, branch: str) -> str | None:
        response = self._get(f"/git/ref/heads/{quote(branch, safe='/')}")
        return None if response is None else str(response.json()["object"]["sha"])

    def file(self, path: str, ref: str) -> RepoFile | None:
        response = self._get(f"/contents/{quote(path, safe='/')}", {"ref": ref})
        if response is None:
            return None
        data = response.json()
        text = base64.b64decode(str(data.get("content", "")).replace("\n", "")).decode("utf-8")
        return RepoFile(text=text, sha=str(data["sha"]))
