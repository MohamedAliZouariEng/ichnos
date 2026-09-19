"""Issues for an approved plan (ADR-0017): the Epic first, then Stories that reference it.

Bodies follow the convention Phase 2's sync parses (## Parent, ## Source specification), so the
links appear on the next sync. {epic} and {S-n} placeholders are the only parts filled in at
execution time, with the numbers GitHub assigns.
"""

from typing import Any

from ichnos.github.writer import Created, GitHubWriteError, GitHubWriter

EPIC = "{epic}"
LABELS = {
    "type:epic": "5319e7",
    "type:story": "1d76db",
    "status:draft": "fbca04",
    "agent:generated": "ededed",
    "priority:must": "b60205",
    "priority:should": "d93f0b",
    "priority:could": "c2e0c6",
}


class PartialIssues(GitHubWriteError):
    """GitHub refused an Issue after others were created; `partial` lists those."""

    def __init__(self, message: str, partial: dict[str, Any]) -> None:
        super().__init__(message)
        self.partial = partial


def _footer(approver: str) -> str:
    return f"---\nCreated by Ichnos after {approver} approved this exact text."


def _requirements(ids: list[str], statements: dict[str, str]) -> list[str]:
    return [f"- {rid}: {statements.get(rid, '')}".rstrip(": ") for rid in ids]


def epic_body(
    plan: dict[str, Any], brd_path: str, statements: dict[str, str], approver: str
) -> str:
    ids = list(statements)
    lines = [
        plan["epic_summary"] or plan["epic_title"],
        "",
        "## Source specification",
        f"- {brd_path}",
    ]
    lines += ["", "## Requirements", *_requirements(ids, statements)]
    if plan.get("exclusions"):
        lines += ["", "## Out of scope", *[f"- {item}" for item in plan["exclusions"]]]
    return "\n".join([*lines, "", _footer(approver)]) + "\n"


def story_body(
    story: dict[str, Any], brd_path: str, statements: dict[str, str], approver: str
) -> str:
    lines = [story["user_story"] or story["title"], "", "## Parent", f"- Epic: #{EPIC}"]
    lines += ["", "## Source specification", f"- {brd_path}"]
    lines += ["", "## Requirements", *_requirements(story["requirement_ids"], statements)]
    criteria = [f"- [ ] {c['id']}: {c['text']}" for c in story["acceptance_criteria"]]
    lines += ["", "## Acceptance criteria", *(criteria or ["- [ ] (none)"])]
    if story.get("depends_on"):
        lines += [
            "",
            "## Dependencies",
            *[f"- Depends on #{{{key}}}" for key in story["depends_on"]],
        ]
    return "\n".join([*lines, "", _footer(approver)]) + "\n"


def build_issues(
    plan: dict[str, Any],
    *,
    approver: str,
    repository: str,
    brd_path: str,
    statements: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """(payload, summary) for a create_issues action."""
    stories = [
        {
            "key": story["key"],
            "title": story["title"],
            "body": story_body(story, brd_path, statements, approver),
            "labels": [
                "type:story",
                "status:draft",
                "agent:generated",
                f"priority:{story['priority']}",
            ],
        }
        for story in plan["stories"]
    ]
    payload = {
        "kind": "create_issues",
        "approver": approver,
        "repository": repository,
        "labels": LABELS,
        "epic": {
            "title": plan["epic_title"],
            "body": epic_body(plan, brd_path, statements, approver),
            "labels": ["type:epic", "status:draft", "agent:generated"],
        },
        "stories": stories,
    }
    return payload, f"Create 1 Epic and {len(stories)} Stories: {plan['epic_title']}"


def _fill(body: str, numbers: dict[str, int]) -> str:
    for key, number in numbers.items():
        body = body.replace(f"#{{{key}}}", f"#{number}")
    for key in [token[2:-1] for token in _tokens(body)]:
        body = body.replace(f"#{{{key}}}", key)  # a Story not created yet keeps its key
    return body


def _tokens(body: str) -> list[str]:
    found, start = [], 0
    while (index := body.find("#{", start)) != -1:
        end = body.find("}", index)
        if end == -1:
            break
        found.append(body[index : end + 1])
        start = end + 1
    return found


def run_create_issues(writer: GitHubWriter, payload: dict[str, Any]) -> dict[str, Any]:
    """Labels, then the Epic, then each Story with the numbers known so far."""
    writer.ensure_labels(payload["labels"])
    epic_spec = payload["epic"]
    epic: Created = writer.create_issue(
        title=epic_spec["title"], body=epic_spec["body"], labels=epic_spec["labels"]
    )
    result: dict[str, Any] = {
        "epic": {"title": epic_spec["title"], "number": epic.number, "url": epic.url},
        "stories": [],
    }
    numbers = {"epic": epic.number}
    for story in payload["stories"]:
        try:
            created = writer.create_issue(
                title=story["title"], body=_fill(story["body"], numbers), labels=story["labels"]
            )
        except GitHubWriteError as exc:
            raise PartialIssues(
                f"{exc} (after {len(result['stories']) + 1} Issues)", result
            ) from exc
        numbers[story["key"]] = created.number
        result["stories"].append(
            {
                "key": story["key"],
                "title": story["title"],
                "number": created.number,
                "url": created.url,
            }
        )
    return result
