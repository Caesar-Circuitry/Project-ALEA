"""Remove finished agent worktrees under .claude/worktrees/ and their leftover branches."""

from __future__ import annotations

import subprocess
from pathlib import Path

WORKTREE_DIR = Path(".claude") / "worktrees"
BRANCH_PREFIX = "worktree-agent-"


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def parse_worktrees(porcelain: str) -> list[Path]:
    """Worktree paths from `git worktree list --porcelain` output."""
    prefix = "worktree "
    return [Path(ln[len(prefix) :]) for ln in porcelain.splitlines() if ln.startswith(prefix)]


def is_under(path: Path, parent: Path) -> bool:
    """True when `path` is strictly inside `parent`."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return path.resolve() != parent.resolve()


def parse_branches(output: str) -> dict[str, str]:
    """Map branch name to commit from `for-each-ref --format='%(refname:short) %(objectname)'`."""
    branches: dict[str, str] = {}
    for line in output.splitlines():
        name, _, sha = line.rpartition(" ")
        if name:
            branches[name] = sha
    return branches


def stale_branches(branches: dict[str, str], main_sha: str) -> list[str]:
    """`worktree-agent-*` branches that point at the same commit as main."""
    return sorted(
        n for n, sha in branches.items() if n.startswith(BRANCH_PREFIX) and sha == main_sha
    )


def main() -> int:
    top = git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print("not inside a git repository")
        return 1
    paths = parse_worktrees(git("worktree", "list", "--porcelain").stdout)
    if not paths:
        print("no worktrees found")
        return 1
    main_root = paths[0]  # the main checkout is always listed first
    here = Path(top.stdout.strip()).resolve()
    for path in paths[1:]:
        if not is_under(path, main_root / WORKTREE_DIR):
            continue
        if path.resolve() == here:
            print(f"skip {path}: current worktree")
            continue
        if git("-C", str(path), "status", "--porcelain").stdout.strip():
            print(f"skip {path}: uncommitted changes")
            continue
        result = git("worktree", "remove", str(path), cwd=main_root)
        if result.returncode == 0:
            print(f"removed worktree {path}")
        else:
            print(f"skip {path}: {result.stderr.strip()}")
    git("worktree", "prune", cwd=main_root)
    print("pruned worktree records")
    refs = git(
        "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", cwd=main_root
    )
    branches = parse_branches(refs.stdout)
    main_sha = branches.get("main")
    if main_sha is None:
        print("no local main branch; leaving branches alone")
        return 0
    for name in stale_branches(branches, main_sha):
        result = git("branch", "-d", name, cwd=main_root)
        if result.returncode == 0:
            print(f"deleted branch {name}")
        else:
            print(f"kept branch {name}: {result.stderr.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
