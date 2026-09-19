"""A tiny in-memory GitHub REST API for sync tests."""

import base64
import hashlib
import re
from typing import Any
from urllib.parse import unquote

import httpx

REPO = r"/repos/[^/]+/[^/]+"
Json = dict[str, Any]


def gh_issue(
    number: int,
    title: str,
    updated: str,
    *,
    body: str = "",
    labels: tuple[str, ...] = (),
    state: str = "open",
    pull: bool = False,
) -> Json:
    kind = "pull" if pull else "issues"
    data: Json = {
        "id": 1000 + number,
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "state_reason": None,
        "user": {"login": "alice"},
        "labels": [{"name": name} for name in labels],
        "milestone": None,
        "html_url": f"https://github.com/o/r/{kind}/{number}",
        "created_at": "2026-09-19T09:00:00Z",
        "updated_at": updated,
        "closed_at": None,
    }
    if pull:
        data["pull_request"] = {"url": f"https://api.github.com/repos/o/r/pulls/{number}"}
    return data


def gh_comment(comment_id: int, number: int, body: str, updated: str) -> Json:
    return {
        "id": comment_id,
        "issue_url": f"https://api.github.com/repos/o/r/issues/{number}",
        "user": {"login": "sara"},
        "body": body,
        "html_url": f"https://github.com/o/r/issues/{number}#issuecomment-{comment_id}",
        "created_at": updated,
        "updated_at": updated,
    }


def gh_commit(sha: str, message: str, date: str) -> Json:
    return {
        "sha": sha,
        "html_url": f"https://github.com/o/r/commit/{sha}",
        "author": {"login": "alice"},
        "commit": {
            "message": message,
            "author": {"name": "Alice", "date": date},
            "committer": {"date": date},
        },
    }


class FakeGitHub:
    def __init__(self, files: dict[str, str], branch: str = "main") -> None:
        self.files = files
        self.branch = branch
        self.requests: list[str] = []
        self.issues: list[Json] = []
        self.comments: list[Json] = []
        self.commits: list[Json] = []
        self.pulls: dict[int, Json] = {}
        self.reviews: dict[int, list[Json]] = {}
        self.review_comments: dict[int, list[Json]] = {}
        self.pr_files: dict[int, list[Json]] = {}
        self.pr_commits: dict[int, list[Json]] = {}

    @staticmethod
    def blob_sha(text: str) -> str:
        return hashlib.sha1(text.encode()).hexdigest()

    @property
    def head(self) -> str:
        digest = hashlib.sha1()
        for path in sorted(self.files):
            digest.update(f"{path}:{self.blob_sha(self.files[path])}\n".encode())
        return digest.hexdigest()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        since = request.url.params.get("since")

        def after(value: str) -> bool:
            return since is None or value >= since

        if match := re.fullmatch(rf"{REPO}/branches/(.+)", path):
            if unquote(match.group(1)) != self.branch:
                return httpx.Response(404, json={"message": "Branch not found"})
            return httpx.Response(200, json={"commit": {"sha": self.head}})
        if match := re.fullmatch(rf"{REPO}/git/trees/(\w+)", path):
            if match.group(1) != self.head:
                return httpx.Response(404, json={"message": "Not Found"})
            tree = [
                {"path": p, "type": "blob", "sha": self.blob_sha(t), "size": len(t.encode())}
                for p, t in sorted(self.files.items())
            ]
            return httpx.Response(200, json={"truncated": False, "tree": tree})
        if match := re.fullmatch(rf"{REPO}/git/blobs/(\w+)", path):
            for text in self.files.values():
                if self.blob_sha(text) == match.group(1):
                    content = base64.b64encode(text.encode()).decode()
                    return httpx.Response(200, json={"encoding": "base64", "content": content})
        if re.fullmatch(rf"{REPO}/issues/comments", path):
            found = [c for c in self.comments if after(c["updated_at"])]
            return httpx.Response(200, json=sorted(found, key=lambda c: c["updated_at"]))
        if re.fullmatch(rf"{REPO}/issues", path):
            found = [i for i in self.issues if after(i["updated_at"])]
            return httpx.Response(200, json=sorted(found, key=lambda i: i["updated_at"]))
        if re.fullmatch(rf"{REPO}/commits", path):
            found = [c for c in self.commits if after(c["commit"]["committer"]["date"])]
            return httpx.Response(200, json=found)
        if match := re.fullmatch(rf"{REPO}/pulls/(\d+)", path):
            pull = self.pulls.get(int(match.group(1)))
            return httpx.Response(200 if pull else 404, json=pull or {"message": "Not Found"})
        if match := re.fullmatch(rf"{REPO}/pulls/(\d+)/(reviews|comments|files|commits)", path):
            sources = {
                "reviews": self.reviews,
                "comments": self.review_comments,
                "files": self.pr_files,
                "commits": self.pr_commits,
            }
            return httpx.Response(200, json=sources[match.group(2)].get(int(match.group(1)), []))
        return httpx.Response(404, json={"message": "Not Found"})
