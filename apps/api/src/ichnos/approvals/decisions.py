"""Decisions proposed while planning a Story, published as OKF Decision concepts (ADR-0020).

The ADR is written from the plan's current version, cites the pack items it names, and goes
through the same approved documentation pull request as a BRD.
"""

import datetime as dt
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.approvals.publish import LOG, add_index_entry, add_log_line
from ichnos.approvals.service import ApprovalError
from ichnos.db.models import Document
from ichnos.github.contents import ContentsReader
from ichnos.okf import render_document
from ichnos.workflows.specification import findings_of

ADR_FILE = re.compile(r"^docs/adr/(\d{4})-")
ADR_INDEX = "docs/adr/index.md"
DOC_ROLES = ("brd", "techspec", "adr")


def proposed_decisions(markdown: str) -> list[dict[str, Any]]:
    """The '### title' subsections of a plan's Proposed decisions section."""
    parts = markdown.split("\n## Proposed decisions\n", 1)
    if len(parts) < 2:
        return []
    section = parts[1].split("\n## ", 1)[0]
    found = []
    for block in re.split(r"^### ", section, flags=re.M)[1:]:
        title, _, rest = block.partition("\n")
        context = re.search(r"\*\*Context\.\*\*\s*(.+)", rest)
        decision = re.search(r"\*\*Decision\.\*\*\s*(.+)", rest)
        sources = re.search(r"^Sources:\s*(.+)$", rest, re.M)
        if title.strip() and decision:
            found.append(
                {
                    "title": title.strip(),
                    "context": context.group(1).strip() if context else "",
                    "decision": decision.group(1).strip(),
                    "cites": [c.strip().upper() for c in sources.group(1).split(",")]
                    if sources
                    else [],
                }
            )
    return found


def next_adr_number(session: Session, workspace_id: str) -> int:
    paths = session.scalars(select(Document.path).where(Document.workspace_id == workspace_id))
    numbers = [int(match.group(1)) for path in paths if (match := ADR_FILE.match(path))]
    return max(numbers, default=0) + 1


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].rstrip("-") or "decision"


def build_decision(
    *,
    proposal: dict[str, Any],
    number: int,
    story: int,
    plan_ref: dict[str, Any],
    pack_items: list[dict[str, Any]],
    approver: str,
    model: str,
    reader: ContentsReader,
    repository: str,
    base_branch: str,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(payload, base, summary) for a docs_pull_request that adds one ADR."""
    name = f"{number:04d}-{_slug(proposal['title'])}.md"
    path = f"docs/adr/{name}"
    title = f"ADR-{number:04d}: {proposal['title']}"
    description = proposal["decision"].split(". ")[0].rstrip(".")[:200] + "."
    at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    by_id = {item["id"]: item for item in pack_items}
    sources = []
    for cite in proposal["cites"]:
        item = by_id.get(cite)
        if item and item["role"] in DOC_ROLES:
            resource = "/" + item["source"].split("@")[0].removeprefix("docs/")
            sources.append({"id": cite.lower(), "resource": resource, "title": item["title"]})
    frontmatter: dict[str, Any] = {
        "type": "Decision",
        "title": title,
        "description": description,
        "tags": ["adr"],
        "status": "stable",
        "generated": {"by": model, "at": at},
        "verified": {"by": approver, "at": at},
    }
    if sources:
        frontmatter["sources"] = sources
    frontmatter["ichnos"] = {"adr_number": number, "story": story, "plan": plan_ref}
    context = proposal["context"] or f"Proposed while planning Story #{story}."
    body = (
        "\n".join(
            [
                "",
                "# Context",
                "",
                context + "".join(f"[^{s['id']}]" for s in sources),
                "",
                "# Decision",
                "",
                proposal["decision"],
                "",
                "# Consequences",
                "",
                f"- Proposed while planning Story #{story}; "
                "the team reviews it in this pull request.",
                "",
                *[f"[^{s['id']}]: {s['title']}" for s in sources],
            ]
        ).rstrip("\n")
        + "\n"
    )
    content = render_document(frontmatter, body)
    errors = sorted({f["code"] for f in findings_of(path, content) if f["level"] == "error"})
    if errors:
        raise ApprovalError(409, "The decision is not valid OKF: " + ", ".join(errors))

    head = reader.head(base_branch)
    if head is None:
        raise ApprovalError(400, f"Branch {base_branch} does not exist in {repository}.")
    current = {p: reader.file(p, base_branch) for p in (path, ADR_INDEX, LOG)}
    if current[path] is not None:
        raise ApprovalError(409, f"{path} already exists.")
    index = current[ADR_INDEX]
    files = {
        path: content,
        ADR_INDEX: add_index_entry(
            index.text if index else None,
            "Architecture Decision Records",
            f"* [{title}]({name}) - {description}",
        ),
    }
    log = current[LOG]
    if log is not None:
        files[LOG] = add_log_line(
            log.text,
            now.date().isoformat(),
            f"* **Creation**: Added [ADR-{number:04d}](/adr/{name}), "
            f"proposed while planning Story #{story}.",
        )
    payload = {
        "kind": "docs_pull_request",
        "approver": approver,
        "repository": repository,
        "base_branch": base_branch,
        "branch": f"ichnos/adr-{number:04d}-{_slug(proposal['title'])}",
        "commit_message": f"docs: propose {title}",
        "title": f"Propose {title}",
        "body": (
            f"Proposes {title}, suggested while planning Story #{story}.\n\n"
            f"- Plan: `{plan_ref['path']}`, version {plan_ref['version']}\n\n"
            "## AI assistance\n\n"
            f"- Generated by Ichnos ({model}); {approver} approved proposing it.\n"
            "- A person reviews and merges it on GitHub; Ichnos never merges.\n"
        ),
        "files": [{"path": p, "content": c} for p, c in files.items()],
    }
    base = {
        "head_sha": head,
        "files": {p: (f.sha if f else None) for p, f in current.items() if p in files},
    }
    return payload, base, f"Propose {title}"
