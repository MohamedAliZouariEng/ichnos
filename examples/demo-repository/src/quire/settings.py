"""Workspace settings."""

from dataclasses import dataclass


@dataclass
class WorkspaceSettings:
    name: str
    allow_guest_links: bool = False
