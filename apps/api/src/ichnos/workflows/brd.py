"""The requirements workflow (Phase 3): retrieval -> requirements -> specification."""

from ichnos.workflows.engine import Stage
from ichnos.workflows.requirements import describe_requirements, requirements_stage
from ichnos.workflows.retrieval import describe_retrieval, retrieval_stage
from ichnos.workflows.specification import describe_specification, specification_stage

WORKFLOW_TYPE = "requirements"
STAGES = [
    Stage("retrieval", retrieval_stage, describe_retrieval),
    Stage("requirements", requirements_stage, describe_requirements),
    Stage("specification", specification_stage, describe_specification),
]
