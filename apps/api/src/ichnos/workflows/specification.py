"""Specification stage (ADR-0014): code renders the enforced brief as an OKF BRD concept.

The model never writes the Markdown, so every draft is OKF-conformant by construction and
every requirement carries footnotes to the material it came from.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

from ichnos.api.intake import proposed_path, slugify
from ichnos.db.models import Artifact, ArtifactVersion, Source
from ichnos.okf import parse_document, render_document
from ichnos.workflows.engine import Data, StageContext, StageFailed
from ichnos.workflows.requirements import Brief, Point

BUNDLE_PREFIX = "docs/"
EMPTY = "None identified."


def _text(value: str) -> str:
    """Link text without brackets that would break Markdown links."""
    return " ".join(value.replace("[", "(").replace("]", ")").split())


def _bundle_path(path: str) -> str:
    return "/" + path.removeprefix(BUNDLE_PREFIX)


@dataclass(frozen=True)
class Reference:
    id: str
    title: str
    resource: str | None

    @property
    def label(self) -> str:
        return self.id.lower()

    def footnote(self) -> str:
        if self.resource:
            return f"[^{self.label}]: [{_text(self.title)}]({self.resource})"
        return f"[^{self.label}]: {_text(self.title)}"


def build_references(
    sources: list[dict[str, Any]], rows: dict[str, Source], context: list[dict[str, Any]]
) -> dict[str, Reference]:
    """What each citation id (S1, C2, ...) points to."""
    refs: dict[str, Reference] = {}
    for source in sources:
        row = rows.get(str(source["source_id"]))
        path = None
        if row is not None:
            path = row.document_path if row.kind == "document" else proposed_path(row)
        resource = _bundle_path(path) if path else None
        refs[source["id"]] = Reference(source["id"], str(source["title"]), resource)
    for item in context:
        kind, key, cid = item["kind"], str(item["key"]), item["id"]
        if kind == "document":
            refs[cid] = Reference(cid, str(item.get("title") or key), _bundle_path(key))
        elif kind in ("issue", "pull_request"):
            name = f"{'Issue' if kind == 'issue' else 'Pull request'} #{key}"
            if item.get("title"):
                name += f": {item['title']}"
            refs[cid] = Reference(cid, name, item.get("url"))
        else:
            name = f"Commit {key[:7]}"
            if item.get("heading"):
                name += f": {item['heading']}"
            refs[cid] = Reference(cid, name, None)
    return refs


def render_brd(brief: Brief, refs: dict[str, Reference], *, model: str, at: str) -> tuple[str, str]:
    """The BRD as OKF Markdown, and its future path in the repository."""
    used: list[str] = []

    def cite(citations: list[str]) -> str:
        marks: list[str] = []
        for cid in citations:
            if cid in refs:
                if cid not in used:
                    used.append(cid)
                marks.append(f"[^{refs[cid].label}]")
        return "".join(marks)

    def points(items: list[Point]) -> list[str]:
        return [f"- {p.text}{cite(p.citations)}" for p in items] or [EMPTY]

    lines = ["", "# Summary", "", brief.problem or brief.title, ""]
    lines += ["# Goals", "", *points(brief.goals), "", "# Requirements", ""]
    for req in brief.requirements:
        statement = f"**{req.priority.capitalize()}.** {req.statement}{cite(req.citations)}"
        lines += [f"## {req.id}", "", statement, ""]
        if req.rationale:
            lines += [f"Rationale: {req.rationale}", ""]
        if req.acceptance_criteria:
            lines += ["Acceptance criteria:", ""]
            lines += [f"- **{c.id}**: {c.text}" for c in req.acceptance_criteria]
            lines.append("")
    sections = (
        ("Assumptions", brief.assumptions),
        ("Open questions", brief.open_questions),
        ("Risks", brief.risks),
        ("Out of scope", brief.out_of_scope),
    )
    for heading, items in sections:
        lines += [f"# {heading}", "", *points(items), ""]
    lines += [refs[cid].footnote() for cid in used]
    body = "\n".join(lines).rstrip() + "\n"

    listed = [cid for cid in refs if cid.startswith("S")]
    listed += [cid for cid in used if cid.startswith("C")]
    sources = [
        {"id": refs[cid].label, "resource": refs[cid].resource, "title": refs[cid].title}
        for cid in listed
        if refs[cid].resource
    ]
    count = len(brief.requirements)
    frontmatter: dict[str, Any] = {
        "type": "BRD",
        "title": brief.title,
        "description": f"Business requirements drafted from the cited sources: {count} "
        "requirements, each citing the material it came from.",
        "tags": ["brd", "requirements"],
        "status": "draft",
        "generated": {"by": model, "at": at},
        "sources": sources,
    }
    return render_document(frontmatter, body), f"docs/specs/{slugify(brief.title)}/brd.md"


def findings_of(path: str, markdown: str) -> list[dict[str, Any]]:
    """OKF findings of one document, in the shape stored on versions."""
    parsed = parse_document(path, markdown)
    return [
        {"level": f.level, "code": f.code, "message": f.message, "line": f.line}
        for f in parsed.findings
    ]


def specification_stage(data: Data, context: StageContext) -> Data:
    if "brief" not in data:
        raise StageFailed("the requirements stage produced no brief")
    brief = Brief.model_validate(data["brief"])
    model = str(data.get("model") or "ichnos/unknown")
    sources = list(data.get("sources", []))
    items = list(data.get("context", []))
    at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with context.factory() as session:
        rows: dict[str, Source] = {}
        for source in sources:
            row = session.get(Source, str(source["source_id"]))
            if row is not None:
                rows[row.id] = row
        markdown, path = render_brd(
            brief, build_references(sources, rows, items), model=model, at=at
        )
        findings = findings_of(path, markdown)
        errors = sorted({f["code"] for f in findings if f["level"] == "error"})
        if errors:
            raise StageFailed("the rendered BRD is not valid OKF: " + ", ".join(errors))
        artifact = Artifact(
            workspace_id=context.workspace_id,
            kind="brd",
            title=brief.title[:300],
            slug=path.split("/")[2],
            status="draft",
            run_id=context.run_id,
            source_ids=[str(source["source_id"]) for source in sources],
            current_version=1,
        )
        session.add(artifact)
        session.flush()
        session.add(
            ArtifactVersion(
                artifact_id=artifact.id,
                number=1,
                content=markdown,
                origin="generated",
                actor=model,
                findings=findings,
            )
        )
        session.commit()
        artifact_id = artifact.id
    return {
        "result": {
            "artifact_id": artifact_id,
            "version": 1,
            "path": path,
            "findings": len(findings),
            "requirements": len(brief.requirements),
        }
    }


def describe_specification(update: Data) -> str:
    result = update.get("result", {})
    return f"BRD drafted for {result.get('path')} ({result.get('findings', 0)} OKF findings)"
