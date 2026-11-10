"""Shared helpers for the team hooks: read `.claude/repo.json`, map files to units, run checks.

Nothing here names a project path or command; all of that comes from `repo.json`. Pure stdlib.
"""

import fnmatch
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

CONTAINER = "alea-dev"
MAX_BLOCKS = 3


def read_payload() -> dict:
    """The hook input from stdin; an empty dict when it cannot be read."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def project_root(payload: dict | None = None) -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd") or "."
    return Path(raw).resolve()


def work_dir(payload: dict, root: Path) -> Path:
    """The agent's own checkout: its worktree when it has one, else the project root."""
    cwd = Path(payload.get("cwd") or root).resolve()
    return cwd if (cwd / ".claude" / "repo.json").is_file() else root


def load_config(root: Path) -> dict:
    return json.loads((root / ".claude" / "repo.json").read_text(encoding="utf-8"))


def rel_path(raw: str, root: Path) -> str | None:
    """`raw` as a posix path relative to `root`, or None when it lies outside."""
    path = Path(raw)
    path = path if path.is_absolute() else root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def matches(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) or rel.startswith(g.rstrip("*")) for g in globs if g)


def unit_for(rel: str, config: dict) -> dict | None:
    """The unit with the longest matching prefix; the empty prefix is the catch-all."""
    best: tuple[int, dict] | None = None
    for unit in config.get("units", []):
        for prefix in unit.get("prefixes", []):
            if rel.startswith(prefix) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), unit)
    return best[1] if best else None


def units_for(files: list[str], config: dict) -> list[dict]:
    seen: dict[str, dict] = {}
    for rel in files:
        unit = unit_for(rel, config)
        if unit:
            seen.setdefault(unit["name"], unit)
    return list(seen.values())


def changed_files(cwd: Path) -> list[str]:
    """Modified, staged and untracked files of the working tree, relative to its top."""
    files: set[str] = set()
    for args in (["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        files.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return sorted(files)


def container_prefix(cwd: Path, root: Path) -> list[str]:
    """`docker exec` prefix when the dev container runs and cwd is inside the project."""
    try:
        cwd.relative_to(root)
        proc = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"name=^{CONTAINER}$"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    return ["docker", "exec", "-w", cwd.as_posix(), CONTAINER]


def run_check(
    command: str, cwd: Path, root: Path, extra: list[str] | None = None
) -> tuple[int, str]:
    """Run one repo.json command without a shell. Returns (exit code, combined output)."""
    argv = shlex.split(command) + (extra or [])
    override = os.environ.get("ALEA_HOOK_PYTHON")  # tests only: `uv run X` -> `<python> -m X`
    if override and argv[:2] == ["uv", "run"]:
        argv = [override, "-m", *argv[2:]]
        prefix: list[str] = []
    else:
        prefix = container_prefix(cwd, root)
    try:
        proc = subprocess.run(
            [*prefix, *argv], cwd=cwd, capture_output=True, text=True, timeout=840
        )
    except Exception as exc:
        return 1, f"could not run `{command}`: {type(exc).__name__}: {exc}"
    return proc.returncode, proc.stderr + proc.stdout  # stdout last: its final line is the summary


def summary_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def counter_path(payload: dict, key: str) -> Path:
    base = Path(payload.get("scratchpad_dir") or tempfile.gettempdir())
    safe = "".join(c if c.isalnum() else "-" for c in key)[:80]
    return base / f"alea-gate-{safe}.count"


def read_count(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8"))
    except Exception:
        return 0


def bump_count(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(read_count(path) + 1), encoding="utf-8")
    except Exception:
        pass
