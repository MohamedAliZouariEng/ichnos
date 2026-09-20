"""The implementation run (Phase 5): context pack, plan, stored draft. Nothing reaches GitHub.

A draft pull request is proposed afterwards from the stored plan, and waits for approval.
"""

from typing import Any

from ichnos.context.code import pack_with_code
from ichnos.context.pack import PackError
from ichnos.db.models import Workspace
from ichnos.github.contents import ContentsError
from ichnos.llm import ModelProvider
from ichnos.workflows.engine import Data, Stage, StageContext, StageFailed
from ichnos.workflows.implementation import (
    ImplementationPlan,
    draft_implementation,
    render_plan,
    store_plan,
)

WORKFLOW_TYPE = "implementation"


def context_stage(data: Data, context: StageContext) -> Data:
    with context.factory() as session:
        workspace = session.get(Workspace, context.workspace_id)
        if workspace is None:
            raise StageFailed("the workspace no longer exists")
        try:
            pack, notes = pack_with_code(
                session,
                workspace,
                int(data["story"]),
                context.services.get("token"),
                context.services.get("transport"),
            )
        except PackError as exc:
            raise StageFailed(str(exc)) from exc
        except ContentsError as exc:
            raise StageFailed(f"GitHub could not be read: {exc}") from exc
    for note in notes:
        context.note(note)
    return {"pack": pack.as_dict()}


def describe_context(update: Data) -> str:
    pack: dict[str, Any] = update.get("pack", {})
    absent = pack.get("absent") or []
    tail = f"; absent: {', '.join(absent)}" if absent else ""
    return (
        f"Context pack {str(pack.get('hash', ''))[:12]}: {len(pack.get('items', []))} items{tail}"
    )


def plan_stage(data: Data, context: StageContext) -> Data:
    provider: ModelProvider | None = context.services.get("provider")
    if provider is None:
        raise StageFailed("no model provider is configured; see the workspace settings")
    plan, notes, usage = draft_implementation(provider, data["pack"])
    context.usage.merge(usage)
    for note in notes:
        context.note(note)
    return {
        "plan": plan.model_dump(),
        "markdown": render_plan(plan),
        "model": f"ichnos/{provider.model}",
    }


def describe_plan(update: Data) -> str:
    plan: dict[str, Any] = update.get("plan", {})
    return (
        f"{len(plan.get('steps', []))} steps, {len(plan.get('tests', []))} tests, "
        f"{len(plan.get('open_questions', []))} open questions"
    )


def store_stage(data: Data, context: StageContext) -> Data:
    plan = ImplementationPlan.model_validate(data["plan"])
    with context.factory() as session:
        artifact = store_plan(
            session,
            workspace_id=context.workspace_id,
            plan=plan,
            markdown=str(data["markdown"]),
            actor=str(data["model"]),
            run_id=context.run_id,
        )
        session.commit()
        return {
            "result": {
                "artifact_id": artifact.id,
                "story": plan.story,
                "pack_hash": plan.pack_hash,
                "open_questions": len(plan.open_questions),
            }
        }


def describe_store(update: Data) -> str:
    return "Stored the plan as a draft to review"


STAGES = [
    Stage("context", context_stage, describe_context),
    Stage("plan", plan_stage, describe_plan),
    Stage("store", store_stage, describe_store),
]
