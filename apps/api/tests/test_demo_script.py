"""make demo names what is missing and starts nothing until the configuration is complete."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "demo.sh"


def run(tmp_path: Path, env_text: str | None) -> tuple[int, str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "docker-calls"
    stub = bin_dir / "docker"
    stub.write_text(f'#!/usr/bin/env bash\necho "$@" >> {calls}\nexit 0\n')
    stub.chmod(0o755)
    env_file = tmp_path / ".env"
    if env_text is not None:
        env_file.write_text(env_text)
    environ = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ICHNOS_ENV_FILE": str(env_file),
    }
    done = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=environ, timeout=30
    )
    return done.returncode, done.stderr, calls.read_text() if calls.exists() else ""


def test_without_an_env_file_it_says_how_to_create_one(tmp_path: Path) -> None:
    code, err, calls = run(tmp_path, None)
    assert code == 1 and "make demo-repo" in err
    assert "up" not in calls.split()


def test_it_names_every_missing_value_and_starts_nothing(tmp_path: Path) -> None:
    code, err, calls = run(tmp_path, "ICHNOS_GITHUB_TOKEN=\nICHNOS_LLM_PROVIDER=gemini\n")
    assert code == 1
    for name in (
        "ICHNOS_GITHUB_TOKEN",
        "ICHNOS_APPROVER_PASSWORD",
        "DEMO_REPO",
        "ICHNOS_LLM_API_KEY",
    ):
        assert name in err
    assert "ICHNOS_LLM_PROVIDER" not in err.split("first:")[1]
    assert "up" not in calls.split()


def test_ollama_needs_no_api_key(tmp_path: Path) -> None:
    _, err, _ = run(tmp_path, "ICHNOS_LLM_PROVIDER=ollama\n")
    assert "ICHNOS_LLM_API_KEY" not in err
