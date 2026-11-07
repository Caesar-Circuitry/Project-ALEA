"""SessionStart hook: print a short repo status that Claude Code adds to the session context.

At most six lines: branch, `.venv` freshness, golden data present, the ROADMAP row marked next,
number of agent worktrees. Never fails the session: any error is swallowed and the exit is 0.
Pure stdlib.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def current_branch(root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout.strip() or "unknown"


def venv_status(root: Path) -> str:
    venv = root / ".venv"
    if not venv.exists():
        return ".venv missing: run just sync"
    lock = root / "uv.lock"
    if lock.exists() and venv.stat().st_mtime < lock.stat().st_mtime:
        return ".venv is older than uv.lock: run just sync"
    return ".venv is up to date"


def golden_status(root: Path) -> str:
    present = (root / "tests" / "golden" / "golden_shots.npy").is_file()
    return "golden_shots.npy present" if present else "golden_shots.npy MISSING"


def next_roadmap_row(text: str) -> str | None:
    for line in text.splitlines():
        if line.lstrip().startswith("|") and "next" in line.lower():
            return " ".join(line.strip().strip("|").replace("|", " | ").split())
    return None


def count_agent_worktrees(porcelain: str) -> int:
    """Count `worktree <path>` lines of `git worktree list --porcelain` under .claude/worktrees."""
    count = 0
    for line in porcelain.splitlines():
        if not line.startswith("worktree "):
            continue
        parts = Path(line[len("worktree ") :].strip()).parts
        pairs = zip(parts, parts[1:], strict=False)
        if (".claude", "worktrees") in pairs:
            count += 1
    return count


def worktree_count(root: Path) -> int:
    proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return count_agent_worktrees(proc.stdout)


def summary(root: Path) -> list[str]:
    lines: list[str] = []
    steps = [
        lambda: f"branch: {current_branch(root)}",
        lambda: venv_status(root),
        lambda: golden_status(root),
        lambda: _roadmap_line(root),
        lambda: f"agent worktrees: {worktree_count(root)}",
    ]
    for step in steps:
        try:
            line = step()
        except Exception:
            continue
        if line:
            lines.append(line)
    return lines[:6]


def _roadmap_line(root: Path) -> str | None:
    path = root / ".claude" / "ROADMAP.md"
    row = next_roadmap_row(path.read_text(encoding="utf-8")) if path.is_file() else None
    return f"roadmap next: {row}" if row else None


def main() -> int:
    try:
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        print("\n".join(summary(root)))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
