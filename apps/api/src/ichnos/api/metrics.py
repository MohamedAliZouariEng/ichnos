"""Release metrics for a workspace (ADR-0025)."""

from fastapi import APIRouter
from pydantic import BaseModel

from ichnos.api.deps import SessionDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.evaluate.metrics import compute_metrics

router = APIRouter(tags=["evaluation"])


class MetricRead(BaseModel):
    key: str
    label: str
    numerator: int
    denominator: int
    threshold: float
    higher_is_better: bool
    value: float | None
    passed: bool | None
    details: list[str]


@router.get(
    "/api/workspaces/{workspace_id}/metrics",
    response_model=list[MetricRead],
    operation_id="getMetrics",
    responses={404: {"description": "Workspace not found"}},
)
def get_metrics(workspace_id: str, session: SessionDep) -> list[MetricRead]:
    """Linked Stories, valid answers, testable criteria and unapproved writes, by code."""
    workspace = get_workspace_or_404(session, workspace_id)
    return [MetricRead(**metric.as_dict()) for metric in compute_metrics(session, workspace)]
