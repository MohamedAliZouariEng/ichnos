import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run each test away from any real .env file and ICHNOS_* variables."""
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("ICHNOS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("ICHNOS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path
