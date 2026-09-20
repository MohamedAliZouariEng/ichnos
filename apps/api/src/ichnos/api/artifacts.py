"""Artifacts: review, edit and version drafts before approval (ADR-0014)."""

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.api.deps import SessionDep
from ichnos.api.sync import FindingRead
from ichnos.api.workspaces import LOCAL_ACTOR, NOT_FOUND, get_workspace_or_404
from ichnos.db.base import as_utc, utc_now
from ichnos.db.models import Artifact, ArtifactVersion, AuditEvent
from ichnos.workflows.implementation import PLAN_KIND, plan_findings
from ichnos.workflows.specification import findings_of

router = APIRouter(tags=["artifacts"])

MAX_CONTENT = 500_000
EDITABLE = {"draft", "needs-review"}
ARTIFACT_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Artifact not found"}}


class VersionSummary(BaseModel):
    number: int
    origin: str
    actor: str
    parent_number: int | None
    note: str | None
    created_at: dt.datetime
    findings: int


class VersionRead(VersionSummary):
    content: str
    finding_details: list[FindingRead]


class ArtifactSummary(BaseModel):
    id: str
    workspace_id: str
    kind: str
    title: str
    slug: str
    path: str
    status: str
    current_version: int
    run_id: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    findings: int


class ArtifactDetail(ArtifactSummary):
    source_ids: list[str]
    versions: list[VersionSummary]
    current: VersionRead


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    base_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=500)


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=MAX_CONTENT)


def artifact_path(artifact: Artifact) -> str:
    """Where the artifact will live in the repository once approved."""
    if artifact.kind == PLAN_KIND:
        return f"ichnos/plans/{artifact.slug}.md"  # never written to the repository
    return f"docs/specs/{artifact.slug}/{artifact.kind}.md"


def findings_for(artifact: Artifact, content: str) -> list[dict[str, Any]]:
    """OKF findings for BRDs; plan checks for implementation plans."""
    if artifact.kind == PLAN_KIND:
        return plan_findings(content)
    return findings_of(artifact_path(artifact), content)


def _version_summary(version: ArtifactVersion) -> VersionSummary:
    return VersionSummary(
        number=version.number,
        origin=version.origin,
        actor=version.actor,
        parent_number=version.parent_number,
        note=version.note,
        created_at=as_utc(version.created_at),
        findings=len(version.findings or []),
    )


def _version_read(version: ArtifactVersion) -> VersionRead:
    return VersionRead(
        **_version_summary(version).model_dump(),
        content=version.content,
        finding_details=[FindingRead(**finding) for finding in version.findings or []],
    )


def _version(session: Session, artifact_id: str, number: int) -> ArtifactVersion | None:
    return session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id, ArtifactVersion.number == number
        )
    )


def _summary(artifact: Artifact, current: ArtifactVersion | None) -> ArtifactSummary:
    return ArtifactSummary(
        id=artifact.id,
        workspace_id=artifact.workspace_id,
        kind=artifact.kind,
        title=artifact.title,
        slug=artifact.slug,
        path=artifact_path(artifact),
        status=artifact.status,
        current_version=artifact.current_version,
        run_id=artifact.run_id,
        created_at=as_utc(artifact.created_at),
        updated_at=as_utc(artifact.updated_at),
        findings=len(current.findings or []) if current else 0,
    )


def _get(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return artifact


def _detail(session: Session, artifact: Artifact) -> ArtifactDetail:
    versions = session.scalars(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact.id)
        .order_by(ArtifactVersion.number)
    ).all()
    current = next(v for v in versions if v.number == artifact.current_version)
    return ArtifactDetail(
        **_summary(artifact, current).model_dump(),
        source_ids=list(artifact.source_ids or []),
        versions=[_version_summary(version) for version in versions],
        current=_version_read(current),
    )


@router.get(
    "/api/workspaces/{workspace_id}/artifacts",
    response_model=list[ArtifactSummary],
    operation_id="listArtifacts",
    responses=NOT_FOUND,
)
def list_artifacts(workspace_id: str, session: SessionDep) -> list[ArtifactSummary]:
    """Drafts and other artifacts, most recently changed first."""
    get_workspace_or_404(session, workspace_id)
    artifacts = session.scalars(
        select(Artifact)
        .where(Artifact.workspace_id == workspace_id)
        .order_by(Artifact.updated_at.desc())
    ).all()
    return [
        _summary(artifact, _version(session, artifact.id, artifact.current_version))
        for artifact in artifacts
    ]


@router.get(
    "/api/artifacts/{artifact_id}",
    response_model=ArtifactDetail,
    operation_id="getArtifact",
    responses=ARTIFACT_NOT_FOUND,
)
def get_artifact(artifact_id: str, session: SessionDep) -> ArtifactDetail:
    return _detail(session, _get(session, artifact_id))


@router.get(
    "/api/artifacts/{artifact_id}/versions/{number}",
    response_model=VersionRead,
    operation_id="getArtifactVersion",
    responses={404: {"description": "Artifact or version not found"}},
)
def get_artifact_version(artifact_id: str, number: int, session: SessionDep) -> VersionRead:
    """Any past version, exactly as it was saved (versions are append-only)."""
    _get(session, artifact_id)
    version = _version(session, artifact_id, number)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    return _version_read(version)


@router.post(
    "/api/artifacts/{artifact_id}/versions",
    response_model=ArtifactDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="createArtifactVersion",
    responses={
        **ARTIFACT_NOT_FOUND,
        400: {"description": "Empty or unchanged content"},
        409: {"description": "Stale base version, or the artifact is no longer a draft"},
    },
)
def create_artifact_version(
    artifact_id: str, body: VersionCreate, session: SessionDep
) -> ArtifactDetail:
    """Save an edit as a new version; earlier versions never change (ADR-0014)."""
    artifact = _get(session, artifact_id)
    if artifact.status not in EDITABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"This artifact is {artifact.status}; only drafts can change."
        )
    if body.base_version != artifact.current_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Version {artifact.current_version} was saved after you started editing "
            f"version {body.base_version}; reload to see it before saving.",
        )
    current = _version(session, artifact.id, artifact.current_version)
    if not body.content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The content is empty.")
    if current is not None and body.content == current.content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No changes to save.")

    number = artifact.current_version + 1
    findings = findings_for(artifact, body.content)
    errors = [str(f["message"]) for f in findings if f["level"] == "error"]
    if artifact.kind == PLAN_KIND and errors:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The plan was not saved. " + " ".join(errors)
        )
    session.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            number=number,
            content=body.content,
            origin="edited",
            actor=LOCAL_ACTOR,
            parent_number=body.base_version,
            findings=findings,
            note=(body.note or "").strip() or None,
        )
    )
    artifact.current_version = number
    artifact.updated_at = utc_now()
    session.add(
        AuditEvent(
            actor=LOCAL_ACTOR,
            event_type="artifact.version_created",
            workspace_id=artifact.workspace_id,
            details={"artifact_id": artifact.id, "version": number, "findings": len(findings)},
        )
    )
    session.commit()
    session.refresh(artifact)
    return _detail(session, artifact)


@router.post(
    "/api/artifacts/{artifact_id}/validate",
    response_model=list[FindingRead],
    operation_id="validateArtifact",
    responses=ARTIFACT_NOT_FOUND,
)
def validate_artifact(
    artifact_id: str, body: ValidateRequest, session: SessionDep
) -> list[FindingRead]:
    """OKF findings for unsaved content; writes nothing."""
    artifact = _get(session, artifact_id)
    return [FindingRead(**f) for f in findings_for(artifact, body.content)]
