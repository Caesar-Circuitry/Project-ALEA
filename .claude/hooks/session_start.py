"""SessionStart hook: print a short repo status that Claude Code adds to the session context.

Under 20 lines: branch and uncommitted files, `.venv` freshness, golden data present, the
ROADMAP row marked next, number of agent worktrees, then from `.claude/repo.json` the active
profile, the units with their test commands and the open areas. Never fails the session: any
error is swallowed and the exit is 0. Pure stdlib.
"""

import contextlib
import itertools
import json
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
        pairs = itertools.pairwise(parts)
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


def dirty_count(root: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--short"], cwd=root, capture_output=True, text=True, timeout=10
    )
    count = len([line for line in proc.stdout.splitlines() if line.strip()])
    return f"uncommitted files: {count}"


def team_lines(root: Path) -> list[str]:
    """Profile, units and open areas from `.claude/repo.json`; empty when it is missing."""
    path = root / ".claude" / "repo.json"
    if not path.is_file():
        return []
    config = json.loads(path.read_text(encoding="utf-8"))
    prof = config.get("profile_settings", {})
    lines = [
        f"profile: {config.get('profile', '?')} (judges on {prof.get('judge_model', '?')}, "
        f"team cap {prof.get('team_cap', '?')}, team from {prof.get('team_threshold', '?')} "
        f"independent items, plan-critic {prof.get('plan_critic', '?')})"
    ]
    names = ", ".join(unit["name"] for unit in config.get("units", []))
    lines.append(f"units (test commands in .claude/repo.json): {names}")
    for area in config.get("open_areas", [])[:6]:
        lines.append(f"open area: {area['path']}: ask {area['owner']} ({area['note']})")
    return lines


def summary(root: Path) -> list[str]:
    lines: list[str] = []
    steps = [
        lambda: f"branch: {current_branch(root)}",
        lambda: dirty_count(root),
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
    with contextlib.suppress(Exception):
        lines += team_lines(root)
    return lines[:19]


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
