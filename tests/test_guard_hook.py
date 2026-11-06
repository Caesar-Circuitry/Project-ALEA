"""The Claude Code physics-guard hook blocks writes to the frozen sim files and nothing else."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard_physics.py"
SHOTSIM = "alea/sim/shotsim.py"
STUDY = "alea/sim/study.py"


def run_hook(payload: dict, env: dict[str, str] | None = None) -> int:
    full_env = {k: v for k, v in os.environ.items() if k != "ALEA_ALLOW_PHYSICS_EDIT"}
    full_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
    )
    return proc.returncode


@pytest.mark.parametrize(
    ("tool", "path", "expected"),
    [
        ("Edit", f"/repo/{SHOTSIM}", 2),
        ("Write", STUDY, 2),
        ("Edit", "C:\\repo\\alea\\sim\\study.py", 2),
        ("Edit", "/repo/alea/sim/plots.py", 0),
        ("Write", "/repo/alea/game/biobuzz.py", 0),
    ],
)
def test_file_tools(tool: str, path: str, expected: int) -> None:
    assert run_hook({"tool_name": tool, "tool_input": {"file_path": path}}) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (f"sed -i s/a/b/ {SHOTSIM}", 2),
        (f"mv x {STUDY}", 2),
        (f"echo hi > {SHOTSIM}", 2),
        (f"git mv _incoming/code/shotsim.py {SHOTSIM}", 0),
        (f"cat {SHOTSIM}", 0),
        ("uv run pytest 2>&1 | tail", 0),
    ],
)
def test_bash(command: str, expected: int) -> None:
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": command}}) == expected


def test_bypass_env() -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": SHOTSIM}}
    assert run_hook(payload, {"ALEA_ALLOW_PHYSICS_EDIT": "1"}) == 0


def test_bad_json_is_ignored() -> None:
    proc = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True)
    assert proc.returncode == 0
