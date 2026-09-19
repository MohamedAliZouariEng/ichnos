"""An in-memory GitHub repository for write tests: Git Data API, pulls, Issues and labels.

Blobs, trees and commits are content-addressed like Git's; every request that is not a GET is
recorded in `writes`, which is what the zero-unapproved-writes test checks (ADR-0015).
"""

import base64
import hashlib
import json
from typing import Any
from urllib.parse import unquote

import httpx


def _sha(*parts: str) -> str:
    return hashlib.sha1("\0".join(parts).encode()).hexdigest()


class FakeGitRepo:
    def __init__(
        self,
        owner: str = "octo",
        name: str = "quire",
        files: dict[str, str] | None = None,
        branch: str = "main",
    ) -> None:
        self.owner, self.name = owner, name
        self.prefix = f"/repos/{owner}/{name}"
        self.blobs: dict[str, str] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.refs: dict[str, str] = {}
        self.pulls: list[dict[str, Any]] = []
        self.issues: list[dict[str, Any]] = []
        self.labels: set[str] = set()
        self.writes: list[tuple[str, str]] = []
        tree = self._tree({path: self._blob(text) for path, text in (files or {}).items()})
        self.refs[branch] = self._commit("initial", tree, [])

    def _blob(self, content: str) -> str:
        sha = _sha("blob", content)
        self.blobs[sha] = content
        return sha

    def _tree(self, files: dict[str, str]) -> str:
        sha = _sha("tree", json.dumps(files, sort_keys=True))
        self.trees[sha] = dict(files)
        return sha

    def _commit(self, message: str, tree: str, parents: list[str]) -> str:
        sha = _sha("commit", message, tree, *parents)
        self.commits[sha] = {"tree": tree, "parents": parents, "message": message}
        return sha

    def files_at(self, branch: str) -> dict[str, str]:
        tree = self.trees[self.commits[self.refs[branch]]["tree"]]
        return {path: self.blobs[sha] for path, sha in tree.items()}

    def push(self, branch: str, files: dict[str, str], message: str = "someone else") -> str:
        """Simulate another person committing to a branch."""
        head = self.refs[branch]
        tree = dict(self.trees[self.commits[head]["tree"]])
        tree.update({path: self._blob(text) for path, text in files.items()})
        self.refs[branch] = self._commit(message, self._tree(tree), [head])
        return self.refs[branch]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _created(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        number = len(self.pulls) + len(self.issues) + 1  # GitHub shares one numbering
        url = f"https://github.com/{self.owner}/{self.name}/{kind}/{number}"
        return {**body, "number": number, "html_url": url}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if not path.startswith(self.prefix):
            return httpx.Response(404, json={"message": "Not Found"})
        route = unquote(path[len(self.prefix) :])
        method = request.method
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        if method != "GET":
            self.writes.append((method, route))

        if method == "GET" and route.startswith("/git/ref/heads/"):
            sha = self.refs.get(route.removeprefix("/git/ref/heads/"))
            if sha is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": sha, "type": "commit"}})
        if method == "GET" and route.startswith("/git/commits/"):
            commit = self.commits[route.removeprefix("/git/commits/")]
            return httpx.Response(200, json={"tree": {"sha": commit["tree"]}})
        if method == "GET" and route.startswith("/contents/"):
            ref = request.url.params.get("ref", "main")
            head = self.refs.get(ref)
            tree = self.trees[self.commits[head]["tree"]] if head else {}
            sha = tree.get(route.removeprefix("/contents/"))
            if sha is None:
                return httpx.Response(404, json={"message": "Not Found"})
            content = base64.b64encode(self.blobs[sha].encode()).decode()
            file = {"sha": sha, "type": "file", "encoding": "base64", "content": content}
            return httpx.Response(200, json=file)
        if method == "POST" and route == "/git/blobs":
            return httpx.Response(201, json={"sha": self._blob(body["content"])})
        if method == "POST" and route == "/git/trees":
            files = dict(self.trees[body["base_tree"]])
            files.update({entry["path"]: entry["sha"] for entry in body["tree"]})
            return httpx.Response(201, json={"sha": self._tree(files)})
        if method == "POST" and route == "/git/commits":
            sha = self._commit(body["message"], body["tree"], body["parents"])
            return httpx.Response(201, json={"sha": sha})
        if method == "POST" and route == "/git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            if name in self.refs:
                return httpx.Response(422, json={"message": "Reference already exists"})
            self.refs[name] = body["sha"]
            return httpx.Response(201, json={"ref": body["ref"]})
        if method == "POST" and route == "/pulls":
            pull = self._created("pull", body)
            self.pulls.append(pull)
            return httpx.Response(201, json=pull)
        if method == "POST" and route == "/issues":
            issue = self._created("issues", body)
            self.issues.append(issue)
            return httpx.Response(201, json=issue)
        if method == "GET" and route.startswith("/labels/"):
            if route.removeprefix("/labels/") in self.labels:
                return httpx.Response(200, json={"name": route.removeprefix("/labels/")})
            return httpx.Response(404, json={"message": "Not Found"})
        if method == "POST" and route == "/labels":
            self.labels.add(body["name"])
            return httpx.Response(201, json={"name": body["name"]})
        return httpx.Response(404, json={"message": "Not Found"})
