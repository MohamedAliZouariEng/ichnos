import json

from ichnos.openapi import render

EXPECTED_OPERATIONS = {
    "getHealth",
    "getServerConfig",
    "listWorkspaces",
    "createWorkspace",
    "getWorkspace",
    "updateWorkspace",
    "checkWorkspaceGitHubAccess",
}


def test_contract_lists_all_operations() -> None:
    schema = json.loads(render())
    operations = {
        operation["operationId"] for path in schema["paths"].values() for operation in path.values()
    }
    assert operations >= EXPECTED_OPERATIONS


def test_render_is_deterministic() -> None:
    assert render() == render()
