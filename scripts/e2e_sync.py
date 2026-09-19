#!/usr/bin/env python3
"""End-to-end check of the Phase 2 exit criteria against a running Ichnos and real GitHub.

1. Syncing twice produces no duplicates.
2. Resetting the knowledge and syncing again rebuilds identical knowledge.
3. Every OKF concept has a type and a trust tier, and concepts carry links.

Usage: scripts/e2e_sync.py [--base URL] [--repository owner/name]
Needs a running stack (make up) whose GitHub token can read the repository.
It resets the derived knowledge of that repository's workspace (ADR-0002: all rebuildable).
Standard library only.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_REPOSITORY = "MohamedAliZouariEng/quire-demo"


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None, **params: str) -> tuple[int, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"{self.base}{path}{query}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")


def check(condition: bool, message: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {message}")
    if not condition:
        sys.exit(1)


def fingerprint(api: Api, workspace_id: str) -> dict[str, list[str]]:
    """Everything the API exposes about the workspace's knowledge, in a stable order."""

    def get(path: str, **params: str) -> Any:
        status, data = api.call("GET", f"/api/workspaces/{workspace_id}/{path}", **params)
        if status != 200:
            check(False, f"GET {path} returned {status}: {data}")
        return data

    def rows(values: Any) -> list[str]:
        return sorted(json.dumps(value) for value in values)

    return {
        "documents": rows(
            [d["path"], d["type"], d["trust_tier"], d["findings"]] for d in get("documents")
        ),
        "items": rows(
            [i["number"], i["type"], i["state"], i["labels"]] for i in get("github/items")
        ),
        "links": rows(
            [k["source_kind"], k["source_key"], k["relation"], k["target_key"], k["origin"]]
            for k in get("links")
        ),
        "search": rows(
            [h["source_kind"], h["source_key"], h["heading"]]
            for h in get("search", q="invitation")
        ),
    }


def sync(api: Api, workspace_id: str) -> dict[str, int]:
    status, run = api.call("POST", f"/api/workspaces/{workspace_id}/sync")
    ok = status == 200 and isinstance(run, dict) and run.get("status") == "succeeded"
    detail = f"{run.get('requests')} GitHub requests" if ok else f"HTTP {status}: {run}"
    check(ok, f"sync succeeded ({detail})")
    counts: dict[str, int] = run["counts"]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="Ichnos base URL")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY, help="owner/name to sync")
    args = parser.parse_args()
    api = Api(args.base)

    status, health = api.call("GET", "/healthz")
    check(status == 200 and health.get("search") == "ok", "API healthy, search available")

    _, workspaces = api.call("GET", "/api/workspaces")
    workspace_id = next((w["id"] for w in workspaces if w["repository"] == args.repository), None)
    if workspace_id is None:
        body = {"name": "e2e", "repository": args.repository}
        status, created = api.call("POST", "/api/workspaces", body)
        check(status == 201, f"created a workspace for {args.repository}")
        workspace_id = created["id"]
    base = f"/api/workspaces/{workspace_id}"

    _, access = api.call("POST", f"{base}/github-check")
    readable = bool(access.get("repository_accessible") and access.get("branch_exists"))
    check(readable, f"the token can read {args.repository}: {access.get('message')}")

    status, _ = api.call("DELETE", f"{base}/knowledge")
    check(status == 200, "started from an empty knowledge base")

    first = sync(api, workspace_id)
    added_docs, added_items = first.get("documents_added", 0), first.get("items_added", 0)
    check(added_docs > 0, f"first sync imported {added_docs} documents and {added_items} items")
    before = fingerprint(api, workspace_id)

    second = sync(api, workspace_id)
    changed = {
        key: value
        for key, value in second.items()
        if value and key.endswith(("_added", "_updated", "_deleted"))
    }
    check(not changed, f"second sync changed nothing {changed or ''}".strip())
    check(fingerprint(api, workspace_id) == before, "EXIT 1: syncing twice gives no duplicates")

    status, reset = api.call("DELETE", f"{base}/knowledge")
    deleted = reset.get("deleted", {}) if status == 200 else {}
    check(deleted.get("documents", 0) > 0, f"reset deleted {sum(deleted.values())} derived rows")
    _, documents = api.call("GET", f"{base}/documents")
    check(documents == [], "the knowledge base is empty after the reset")
    sync(api, workspace_id)
    check(fingerprint(api, workspace_id) == before, "EXIT 2: reset and sync rebuild identically")

    _, documents = api.call("GET", f"{base}/documents")
    concepts = [doc for doc in documents if doc["kind"] == "concept"]
    typed = all(doc["type"] and doc["trust_tier"] for doc in concepts)
    check(bool(concepts) and typed, f"all {len(concepts)} concepts have a type and a trust tier")
    linked = 0
    for doc in concepts:
        _, links = api.call("GET", f"{base}/links", kind="document", key=doc["path"])
        linked += bool(links)
    check(linked == len(concepts), f"EXIT 3: {linked} of {len(concepts)} concepts carry links")

    print(f"\nPhase 2 exit criteria hold for {args.repository}.")


if __name__ == "__main__":
    main()
