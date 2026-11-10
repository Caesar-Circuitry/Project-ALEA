"""Test gate: a writer may not hand back, close a task or go idle while its tests are red.

One script, three events (told apart by `hook_event_name`):

- `SubagentStop` (frontmatter of the writer agents): runs `gate_checks` from
  `.claude/repo.json` (lint, format check, the test suite) in the subagent's checkout.
- `TaskCompleted`: for an `impl:` or `test:` task, lints the task's files and runs the tests of
  the units they belong to. Other kinds (`plan:`, `verify:`, `safety:`, `docs:`) pass.
- `TeammateIdle`: for a writer teammate (name matches `writer_name_pattern`), the same over the
  files changed in the working tree.

Exit 2 sends the summary back and keeps the agent working. A unit without a test command
passes. Gives up after three blocks per agent or task so an unfixable failure reaches the lead
instead of looping. Never fails closed: a gate that cannot run lets the agent through, and the
verifier still runs every check. Pure stdlib.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import task_shape
import teamlib

GATED_KINDS = {"impl", "test"}


def lint_targets(files: list[str], cwd: Path, config: dict) -> list[str]:
    frozen = set(config.get("frozen_paths", []))
    return [f for f in files if f.endswith(".py") and f not in frozen and (cwd / f).is_file()]


def scope(payload: dict, cwd: Path, config: dict) -> tuple[str, list[str]] | None:
    """(counter key, files to check) for this event, or None when the gate does not apply."""
    event = payload.get("hook_event_name", "")
    if event == "TaskCompleted":
        parsed = task_shape.subject_paths(str(payload.get("task_subject", "")))
        if parsed is None or parsed[0] not in GATED_KINDS:
            return None
        files = parsed[1] or teamlib.changed_files(cwd)
        return f"task-{payload.get('task_id', 'x')}", files
    if event == "TeammateIdle":
        name = str(payload.get("teammate_name", ""))
        if not re.search(config.get("writer_name_pattern", r"^$"), name):
            return None
        return f"idle-{name}", teamlib.changed_files(cwd)
    agent = payload.get("agent_type")
    if agent and agent not in config.get("writer_agents", []):
        return None
    return f"stop-{payload.get('agent_id', 'main')}", teamlib.changed_files(cwd)


def checks_for(
    event: str, files: list[str], cwd: Path, config: dict
) -> list[tuple[str, list[str]]]:
    """(command, extra arguments) pairs to run, in order."""
    if event not in ("TaskCompleted", "TeammateIdle"):
        return [(cmd, []) for cmd in config.get("gate_checks", [])]
    checks: list[tuple[str, list[str]]] = []
    units = teamlib.units_for(files, config)
    targets = lint_targets(files, cwd, config)
    lint = next((u["lint"] for u in units if u.get("lint")), None)
    if lint and targets:
        checks.append((lint, targets))
    checks += [(u["test"], []) for u in units if u.get("test")]
    return checks


def main() -> int:
    if os.environ.get("ALEA_GATE_SKIP") == "1":
        return 0
    payload = teamlib.read_payload()
    try:
        root = teamlib.project_root(payload)
        cwd = teamlib.work_dir(payload, root)
        config = teamlib.load_config(cwd)
        found = scope(payload, cwd, config)
    except Exception:
        return 0
    if found is None or not found[1]:
        return 0
    key, files = found
    counter = teamlib.counter_path(payload, key)
    blocks = teamlib.read_count(counter)
    if blocks >= teamlib.MAX_BLOCKS:
        return 0
    event = payload.get("hook_event_name", "")
    if event not in ("TaskCompleted", "TeammateIdle") and config.get("gate_setup"):
        teamlib.run_check(config["gate_setup"], cwd, root)
    for command, extra in checks_for(event, files, cwd, config):
        code, output = teamlib.run_check(command, cwd, root, extra)
        if code != 0:
            teamlib.bump_count(counter)
            sys.stderr.write(
                f"Not done yet: `{command}` failed (block {blocks + 1}/{teamlib.MAX_BLOCKS}): "
                f"{teamlib.summary_line(output)}\nFix it and finish again. If the failure is in "
                "a file another teammate owns, message that teammate with the failing lines "
                "instead of editing it.\n" + output[-3000:]
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
