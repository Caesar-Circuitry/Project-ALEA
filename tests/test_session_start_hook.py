"""Pure helpers of the SessionStart hook, run against a tmp project dir."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "session_start.py"
spec = importlib.util.spec_from_file_location("session_start", HOOK)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_venv_missing(tmp_path: Path) -> None:
    assert ".venv missing" in mod.venv_status(tmp_path)


def test_venv_older_than_lock(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    venv.mkdir()
    lock = tmp_path / "uv.lock"
    lock.write_text("x", encoding="utf-8")
    old = time.time() - 1000
    os.utime(venv, (old, old))
    assert "just sync" in mod.venv_status(tmp_path)
    os.utime(venv, (time.time() + 100, time.time() + 100))
    assert "up to date" in mod.venv_status(tmp_path)


def test_golden_status(tmp_path: Path) -> None:
    assert "MISSING" in mod.golden_status(tmp_path)
    golden = tmp_path / "tests" / "golden"
    golden.mkdir(parents=True)
    (golden / "golden_shots.npy").write_bytes(b"x")
    assert "present" in mod.golden_status(tmp_path)


def test_next_roadmap_row() -> None:
    text = "| 3 | a | done |\n| 4 | `setup/04` | Move sim | **next** once 3b merges | x |\n"
    row = mod.next_roadmap_row(text)
    assert row is not None and row.startswith("4 |") and "next" in row
    assert mod.next_roadmap_row("nothing here") is None


def test_worktree_count(tmp_path: Path) -> None:
    assert mod.worktree_count(tmp_path) == 0
    (tmp_path / ".claude" / "worktrees" / "a").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "b").mkdir()
    assert mod.worktree_count(tmp_path) == 2


def test_summary_is_short_and_never_fails(tmp_path: Path) -> None:
    assert len(mod.summary(tmp_path)) <= 6
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "nope")},
    )
    assert proc.returncode == 0
