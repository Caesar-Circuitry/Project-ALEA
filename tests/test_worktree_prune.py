"""Pure parsing helpers of the worktree-prune tool."""

from __future__ import annotations

from pathlib import Path

from alea.tools.worktree_prune import is_under, parse_branches, parse_worktrees, stale_branches

PORCELAIN = """worktree /repo
HEAD abc
branch refs/heads/main

worktree /repo/.claude/worktrees/agent-1
HEAD def
branch refs/heads/worktree-agent-1
"""


def test_parse_worktrees() -> None:
    assert parse_worktrees(PORCELAIN) == [Path("/repo"), Path("/repo/.claude/worktrees/agent-1")]


def test_is_under_is_strict() -> None:
    parent = Path("/repo/.claude/worktrees")
    assert is_under(parent / "agent-1", parent)
    assert not is_under(parent, parent)
    assert not is_under(Path("/repo"), parent)


def test_stale_branches_only_matching_prefix_and_commit() -> None:
    branches = parse_branches(
        "main aaa\nworktree-agent-1 aaa\nworktree-agent-2 bbb\nfeature/x aaa\n"
    )
    assert stale_branches(branches, "aaa") == ["worktree-agent-1"]
