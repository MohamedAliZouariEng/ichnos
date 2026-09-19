"""A tiny in-memory GitHub REST API for sync tests."""

import base64
import hashlib
import re
from urllib.parse import unquote

import httpx

REPO = r"/repos/[^/]+/[^/]+"


class FakeGitHub:
    def __init__(self, files: dict[str, str], branch: str = "main") -> None:
        self.files = files
        self.branch = branch
        self.requests: list[str] = []

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
        return httpx.Response(404, json={"message": "Not Found"})
