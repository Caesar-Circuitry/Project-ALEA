"""PreToolUse hook: block edits to the frozen shot-physics files.

Claude Code pipes the tool call as JSON on stdin. Exit 2 blocks the call and shows stderr to the
model. Set ALEA_ALLOW_PHYSICS_EDIT=1 to bypass (only with the user's explicit approval).
Pure stdlib so it runs on every platform via `uv run --no-project python`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import PurePosixPath

FROZEN = ("alea/sim/shotsim.py", "alea/sim/study.py")
WRITE_HINTS = re.compile(r"(sed\s+-i|>\s*\S|\btee\b|(?<!git )\bmv\b|\bcp\b|\brm\b|\btruncate\b)")


def _norm(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _touches_frozen(text: str) -> str | None:
    norm = _norm(text)
    for f in FROZEN:
        if norm.endswith(f) or f in norm:
            return f
    return None


def main() -> int:
    if os.environ.get("ALEA_ALLOW_PHYSICS_EDIT") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    hit = None
    if tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        hit = _touches_frozen(str(target))
    elif tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if WRITE_HINTS.search(cmd):
            hit = _touches_frozen(cmd)
    if hit:
        sys.stderr.write(
            f"BLOCKED: {hit} holds frozen shot physics (CLAUDE.md rule 1). "
            "Moving the file is fine via git mv; changing it needs the user's explicit approval, "
            "ALEA_ALLOW_PHYSICS_EDIT=1, a passing self-test and a Java comparison on the PR.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
