"""Stop hook for the implementer: it may not finish while lint or tests fail.

Runs `ruff check`, `ruff format --check` and `pytest -m "not gpu and not slow"` in the hook's
cwd (the subagent's worktree or checkout). On failure exits 2 with the output on stderr, which
Claude Code hands back to the subagent as its next instruction. Gives up after three blocks per
agent so an unfixable failure reaches the lead instead of looping. Pure stdlib.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_BLOCKS = 3
CHECKS = [
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
    ["uv", "run", "pytest", "-q", "-x", "-m", "not gpu and not slow"],
]


def main() -> int:
    if os.environ.get("ALEA_GATE_SKIP") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cwd = Path(payload.get("cwd") or Path.cwd())
    if not (cwd / "pyproject.toml").exists():
        return 0
    counter_dir = Path(payload.get("scratchpad_dir") or tempfile.gettempdir())
    counter = counter_dir / f"alea-gate-{payload.get('agent_id', 'main')}.count"
    try:
        blocks = int(counter.read_text()) if counter.exists() else 0
    except Exception:
        blocks = 0
    if blocks >= MAX_BLOCKS:
        return 0
    subprocess.run(
        ["uv", "sync", "--all-extras", "--no-extra", "gpu", "--group", "dev", "-q"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    for check in CHECKS:
        proc = subprocess.run(check, cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            try:
                counter.parent.mkdir(parents=True, exist_ok=True)
                counter.write_text(str(blocks + 1))
            except Exception:
                pass
            tail = (proc.stdout + proc.stderr)[-4000:]
            sys.stderr.write(
                f"Not done yet: `{' '.join(check)}` failed (block {blocks + 1}/{MAX_BLOCKS}). "
                "Fix it, re-run `just lint` and `just test`, then finish.\n" + tail
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
