"""Build a context pack with code read at the commits the sync recorded (ADR-0019)."""

from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.context.pack import ContextPack, build_pack
from ichnos.db.models import RepositoryFile, Workspace
from ichnos.github.contents import ContentsReader


def pack_with_code(
    session: Session,
    workspace: Workspace,
    number: int,
    token: SecretStr | None,
    transport: Any,
    *,
    code: bool = True,
) -> tuple[ContextPack, list[str]]:
    """The pack and notes about it. Raises PackError, or ContentsError if GitHub fails."""
    notes: list[str] = []
    if code and (token is None or not token.get_secret_value()):
        notes.append("Code contents were not fetched: no GitHub token is configured.")
    if not code or token is None or not token.get_secret_value():
        return build_pack(session, workspace, number), notes
    files = {
        f.blob_sha: (f.path, f.commit_sha)
        for f in session.scalars(
            select(RepositoryFile).where(RepositoryFile.workspace_id == workspace.id)
        )
    }
    repository = f"{workspace.repo_owner}/{workspace.repo_name}"
    with ContentsReader(repository, token, transport) as reader:

        def fetch(blob_sha: str) -> str:
            path, commit = files[blob_sha]
            found = reader.file(path, commit)
            return found.text if found else ""

        return build_pack(session, workspace, number, fetch=fetch), notes
