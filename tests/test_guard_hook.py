"""The Claude Code guard hooks: frozen physics files (all agents) and the coordinate-only lead."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
PHYSICS = HOOKS / "guard_physics.py"
LEAD = HOOKS / "guard_lead.py"
SHOTSIM = "alea/sim/shotsim.py"
STUDY = "alea/sim/study.py"


def run_hook(hook: Path, payload: dict, env: dict[str, str] | None = None) -> int:
    full_env = {k: v for k, v in os.environ.items() if k != "ALEA_ALLOW_PHYSICS_EDIT"}
    full_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
    )
    return proc.returncode


# --- guard_physics.py -------------------------------------------------------------------


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
def test_physics_file_tools(tool: str, path: str, expected: int) -> None:
    payload = {"tool_name": tool, "tool_input": {"file_path": path}}
    assert run_hook(PHYSICS, payload) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (f"sed -i s/a/b/ {SHOTSIM}", 2),
        (f"mv x {STUDY}", 2),
        (f"echo hi > {SHOTSIM}", 2),
        (f"git mv _incoming/code/shotsim.py {SHOTSIM}", 0),
        (f"cat {SHOTSIM}", 0),
        ("uv run pytest 2>&1 | tail", 0),
        # false positive: the text mentions alea/sim but the target is another file
        ("sed -i 's/alea\\/sim/alea\\/sim2/' .claude/AGENTIC_WORKFLOW.md", 0),
        (f'echo "see {STUDY}" > notes.txt', 0),
        ("rm alea/sim/plots.py", 0),
        (f"git mv {SHOTSIM} alea/sim/old.py", 0),
        (f"git diff -- {STUDY}", 0),
        # still blocked
        (f"sed -i.bak s/a/b/ {SHOTSIM}", 2),
        (f"echo hi >{STUDY}", 2),
        (f"echo hi>>{STUDY}", 2),
        (f"cp /tmp/x ./alea/sim/../sim/{SHOTSIM.rsplit('/', 1)[1]}", 2),
        (f"rm -f '/repo/{STUDY}'", 2),
        (f"cat a | tee {SHOTSIM}", 2),
    ],
)
def test_physics_bash(command: str, expected: int) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    assert run_hook(PHYSICS, payload) == expected


def test_physics_bypass_env() -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": SHOTSIM}}
    assert run_hook(PHYSICS, payload, {"ALEA_ALLOW_PHYSICS_EDIT": "1"}) == 0


def test_physics_bad_json_is_ignored() -> None:
    proc = subprocess.run(
        [sys.executable, str(PHYSICS)], input="not json", capture_output=True, text=True
    )
    assert proc.returncode == 0


# --- guard_lead.py ----------------------------------------------------------------------


def lead(tool: str, **tool_input: str) -> dict:
    return {"agent_type": "lead", "tool_name": tool, "tool_input": tool_input}


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_lead_file_tools_blocked(tool: str) -> None:
    assert run_hook(LEAD, lead(tool, file_path="alea/web/app.py")) == 2


@pytest.mark.parametrize(
    "command",
    [
        "just test",
        "just lint",
        "just selftest",
        "uv run pytest -q tests/test_import.py",
        "uv run ruff check .",
        "uv run pyright",
        "uv sync --all-extras --no-extra gpu --group dev",
        "git status --short",
        "git diff main -- alea/",
        "git log --oneline -5",
        "git branch -a",
        "ls -la alea/",
        "cat README.md",
        "grep -rn TODO alea | head -20",
        "uv run pytest 2>&1 | tail -5",
        "cd docs && ls",
        "TZ=UTC git log -1",
        "cat a b c",
        'grep -n "a\\|b" file',
        'git -C "/Users/x/Project ALEA/Repo" remote -v',
        "git -C /tmp/repo status --short",
        "git merge-tree --write-tree main feature/x",
        "git show setup/x:.claude/settings.json | head -20",
        "git show HEAD~1:README.md | head",
        "git ls-files alea",
        "git worktree list",
        "git rev-parse --abbrev-ref HEAD",
        "git remote -v",
        "git stash list",
        "git branch --show-current",
        "git fetch origin",
        "uv run pytest 2>&1 | tail -5",
        "just test 2>&1 | tail -5",
        "ls nope 2>/dev/null",
        "wc -l a b; sort a | uniq -c | cut -f1 | tr a b",
        "diff a b",
        "shasum -a 256 a",
        "sha256sum a",
        "stat a && du -sh . && tree -L 1 && file a",
        "env",
        "printenv HOME",
        "which uv && type uv",
        "gh pr view 8",
        "gh pr list --state open",
        "gh pr checks 8",
        "gh pr diff 8",
        "gh run list --limit 3",
        "gh run view 123 --log-failed",
        "gh api repos/o/r/pulls",
        "gh api -X GET repos/o/r/pulls",
        "uv run ruff format --check .",
    ],
)
def test_lead_bash_allowed(command: str) -> None:
    assert run_hook(LEAD, lead("Bash", command=command)) == 0


@pytest.mark.parametrize(
    "command",
    [
        "just fmt",
        "uv run ruff check --fix .",
        "echo hi > notes.txt",
        "ls >> out.txt",
        "cat a | tee b",
        "sed -i s/a/b/ alea/web/app.py",
        "rm -rf build",
        "mv a b",
        "cp a b",
        "touch x",
        "mkdir y",
        "git add -A",
        "git commit -m x",
        "git push origin main",
        "git checkout -b feature/x",
        "python -c \"open('x','w').write('y')\"",
        "uv run python script.py",
        "git status && rm x",
        "find . -name '*.tmp' -delete",
        "uv pip install requests",
        "pip install requests",
        "cat a > b",
        "cat < a",
        "cat a >> b",
        "echo hi 1> b",
        "cat a &> b",
        "cat a | tee b",
        "git -C /tmp/repo commit -m x",
        "git -C /tmp/repo add -A",
        "git merge feature/x",
        "git rebase main",
        "git reset --hard",
        "git switch main",
        "git worktree add ../x",
        "git worktree remove ../x",
        "git branch -d old",
        "git branch -D old",
        "git branch newbranch",
        "git stash",
        "git stash pop",
        "git remote add o url",
        "gh pr create",
        "gh pr merge 8",
        "gh run rerun 1",
        "gh api -X POST repos/o/r/issues",
        "gh api -X DELETE repos/o/r",
        "gh api repos/o/r/issues -f title=x",
        "uv run ruff format .",
        "uv run ruff check --fix .",
        "sort -o out in",
        "env rm x",
        "echo $(rm x)",
        "echo `rm x`",
        "cat a; mv a b",
        "cat a & rm b",
    ],
)
def test_lead_bash_blocked(command: str) -> None:
    assert run_hook(LEAD, lead("Bash", command=command)) == 2


def test_lead_hook_ignores_other_agents() -> None:
    for agent in ("implementer", "docs-writer", "explorer"):
        payload = {"agent_type": agent, "tool_name": "Edit", "tool_input": {"file_path": "x.py"}}
        assert run_hook(LEAD, payload) == 0
        payload = {"agent_type": agent, "tool_name": "Bash", "tool_input": {"command": "rm x"}}
        assert run_hook(LEAD, payload) == 0


def test_lead_hook_ignores_sessions_without_agent() -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}}
    assert run_hook(LEAD, payload) == 0


def test_lead_bad_json_is_ignored() -> None:
    proc = subprocess.run(
        [sys.executable, str(LEAD)], input="not json", capture_output=True, text=True
    )
    assert proc.returncode == 0
