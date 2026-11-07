"""The PostToolUse auto-format hook formats edited .py files and leaves everything else alone."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "autoformat.py"
UGLY = "x   =  {'a':1,\n  'b':2}\nimport os\n"


def run(project: Path, file_path: Path | str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(project),
        "ALEA_RUFF_PYTHON": sys.executable,
    }
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def test_formats_py_inside_project(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text(UGLY, encoding="utf-8")
    proc = run(tmp_path, target)
    assert proc.returncode == 0
    assert target.read_text(encoding="utf-8").startswith('x = {"a": 1')


def test_frozen_file_untouched(tmp_path: Path) -> None:
    frozen = tmp_path / "alea" / "sim" / "shotsim.py"
    frozen.parent.mkdir(parents=True)
    frozen.write_text(UGLY, encoding="utf-8")
    assert run(tmp_path, frozen).returncode == 0
    assert frozen.read_text(encoding="utf-8") == UGLY


def test_non_py_untouched(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text(UGLY, encoding="utf-8")
    assert run(tmp_path, target).returncode == 0
    assert target.read_text(encoding="utf-8") == UGLY


def test_outside_project_untouched(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    outside = tmp_path / "other.py"
    outside.write_text(UGLY, encoding="utf-8")
    assert run(project, outside).returncode == 0
    assert outside.read_text(encoding="utf-8") == UGLY


def test_bad_input_exits_zero() -> None:
    proc = subprocess.run([sys.executable, str(HOOK)], input="nope", capture_output=True, text=True)
    assert proc.returncode == 0
