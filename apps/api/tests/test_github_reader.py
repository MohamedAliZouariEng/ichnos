import base64
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from ichnos.github.reader import GitHubError, GitHubReader, RateLimitExceeded

BASE = "https://api.github.test"
Handler = Callable[[httpx.Request], httpx.Response]


def reader(handler: Handler, etags: dict[str, str] | None = None, **kwargs: int) -> GitHubReader:
    return GitHubReader(
        SecretStr("test-token"),
        base_url=BASE,
        transport=httpx.MockTransport(handler),
        etags=etags,
        **kwargs,
    )


def test_paginate_follows_link_headers() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        page = int(request.url.params.get("page", "1"))
        headers = {}
        if page < 3:
            headers["Link"] = f'<{BASE}/repos/o/r/issues?per_page=100&page={page + 1}>; rel="next"'
        return httpx.Response(200, json=[{"number": page}], headers=headers)

    with reader(handler) as github:
        numbers = [item["number"] for item in github.paginate("/repos/o/r/issues")]
    assert numbers == [1, 2, 3]
    assert seen[0].params["per_page"] == "100"
    assert github.requests == 3


def test_every_request_is_authenticated() -> None:
    auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers["Authorization"])
        return httpx.Response(200, json={"commit": {"sha": "abc"}})

    with reader(handler) as github:
        assert github.branch_head("o", "r", "main") == "abc"
    assert auth == ["Bearer test-token"]


def test_conditional_requests_use_etags() -> None:
    etags: dict[str, str] = {}
    sent: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers.get("If-None-Match"))
        if request.headers.get("If-None-Match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, json=[{"number": 1}], headers={"ETag": '"v1"'})

    with reader(handler, etags) as github:
        first = list(github.paginate("/repos/o/r/issues", conditional=True))
        second = list(github.paginate("/repos/o/r/issues", conditional=True))
    assert first == [{"number": 1}]
    assert second == []
    assert sent == [None, '"v1"']
    assert len(etags) == 1


def test_issues_request_all_states_since_cursor() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=[])

    with reader(handler) as github:
        list(github.issues("o", "r", since="2026-09-19T10:00:00Z"))
    params = seen[0].params
    assert (params["state"], params["sort"], params["direction"]) == ("all", "updated", "asc")
    assert params["since"] == "2026-09-19T10:00:00Z"


@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1790000000"}),
        (429, {"Retry-After": "30"}),
        (403, {"Retry-After": "60"}),
    ],
)
def test_rate_limits_raise_with_reset_time(status: int, headers: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "API rate limit exceeded"}, headers=headers)

    with reader(handler) as github, pytest.raises(RateLimitExceeded) as caught:
        github.get_json("/repos/o/r")
    assert caught.value.reset_at is not None


def test_errors_carry_github_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with reader(handler) as github, pytest.raises(GitHubError) as caught:
        github.get_json("/repos/o/missing")
    assert caught.value.status_code == 404
    assert caught.value.message == "Not Found"
    assert not isinstance(caught.value, RateLimitExceeded)


def test_tree_keeps_blobs_and_refuses_truncated_trees() -> None:
    tree = {
        "truncated": False,
        "tree": [
            {"path": "docs", "type": "tree", "sha": "t1"},
            {"path": "docs/index.md", "type": "blob", "sha": "b1", "size": 120},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tree)

    with reader(handler) as github:
        entries = github.tree("o", "r", "head")
    assert [(entry.path, entry.sha) for entry in entries] == [("docs/index.md", "b1")]

    tree["truncated"] = True
    with reader(handler) as github, pytest.raises(GitHubError):
        github.tree("o", "r", "head")


def test_blob_text_is_decoded() -> None:
    encoded = base64.b64encode("# Glossary\n\nÜnïcode ok\n".encode()).decode()
    wrapped = "\n".join(encoded[i : i + 20] for i in range(0, len(encoded), 20))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"encoding": "base64", "content": wrapped})

    with reader(handler) as github:
        assert github.blob_text("o", "r", "b1") == "# Glossary\n\nÜnïcode ok\n"


def test_page_cap_stops_runaway_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        link = f'<{BASE}/repos/o/r/commits?page=next>; rel="next"'
        return httpx.Response(200, json=[{"sha": "x"}], headers={"Link": link})

    with reader(handler, max_pages=2) as github, pytest.raises(GitHubError):
        list(github.paginate("/repos/o/r/commits"))
