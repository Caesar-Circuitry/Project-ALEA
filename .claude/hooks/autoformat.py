"""PostToolUse hook: format a Python file right after Claude edits it.

Runs `ruff format` and `ruff check --fix` on the edited `.py` file when it lies inside the
project dir and is not a frozen shot-physics file. Never fails: a formatting problem prints a
one-line warning and the edit stays. Always exits 0. Pure stdlib.

`ALEA_RUFF_PYTHON` (tests only) swaps `uv run ruff` for `<that python> -m ruff`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FROZEN = ("alea/sim/shotsim.py", "alea/sim/study.py")


def target_file(payload: dict, project_dir: Path) -> Path | None:
    """The file to format, or None when the hook should leave it alone."""
    tool_input = payload.get("tool_input", {}) or {}
    raw = tool_input.get("file_path")
    if not raw or not str(raw).endswith(".py"):
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = project_dir / path
    path = path.resolve()
    root = project_dir.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    if any(path == root / f for f in FROZEN):
        return None
    return path


def ruff_prefix() -> list[str]:
    python = os.environ.get("ALEA_RUFF_PYTHON")
    return [python, "-m", "ruff"] if python else ["uv", "run", "ruff"]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
        path = target_file(payload, project_dir)
        if path is None:
            return 0
        for args in (["format", str(path)], ["check", "--fix", str(path)]):
            proc = subprocess.run(
                [*ruff_prefix(), *args],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=50,
            )
            # `ruff check --fix` exits 1 when unfixable findings remain; that is not an error here.
            if proc.returncode not in (0, 1) or (args[0] == "format" and proc.returncode):
                first = (proc.stderr or proc.stdout).strip().splitlines()[:1]
                print(f"autoformat: ruff {args[0]} failed on {path.name}: {' '.join(first)}")
    except Exception as exc:  # never undo or block an edit
        print(f"autoformat: skipped ({type(exc).__name__}: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
