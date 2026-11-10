"""PreToolUse hook (Edit, Write, MultiEdit; every agent): tests and proofs are not weakened.

Blocks an edit that (1) removes a test definition that exists on disk or adds a skip or xfail
marker in a file matching `test_globs`, (2) changes or overwrites an existing file under
`append_only_paths` (new files are fine), (3) touches a `protected_paths` file, or (4) removes
a step, job or path filter from a `ci_paths` workflow. Patterns come from `.claude/repo.json`.
Exit 2 blocks the call. Fails closed on unreadable input. Pure stdlib.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teamlib

FILE_TOOLS = {"Edit", "Write", "MultiEdit"}
CI_KEEP = re.compile(
    r"^\s*((-\s+)?(name|uses|run|if):.*|[\w-]+:\s*$|-\s+['\"]?[\w.*/-]+['\"]?\s*$)$", re.M
)
WORKTREE = re.compile(r"^\.claude/worktrees/[^/]+/")


def after_edit(tool: str, tool_input: dict, before: str) -> str:
    """The file text the edit would produce (best effort; unmatched edits change nothing)."""
    if tool == "Write":
        return str(tool_input.get("content", ""))
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    text = before
    for edit in edits or []:
        old, new = str(edit.get("old_string", "")), str(edit.get("new_string", ""))
        if not old:
            continue
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def test_reason(before: str, after: str, config: dict) -> str | None:
    test_def = re.compile(config["test_def_pattern"], re.M)
    skip = re.compile(config["skip_marker_pattern"], re.M)
    removed = sorted(set(test_def.findall(before)) - set(test_def.findall(after)))
    if removed:
        return f"removes test(s) {', '.join(removed)}; tests are fixed or reported, not deleted"
    if len(skip.findall(after)) > len(skip.findall(before)):
        return "adds a skip or xfail marker; a failing test is fixed or reported as FAIL"
    return None


def ci_lines(text: str) -> list[str]:
    """Steps, jobs, conditions and path filters of a workflow; action versions ignored."""
    lines = [m.group(0).strip() for m in CI_KEEP.finditer(text)]
    return [re.sub(r"(uses:\s*\S+?)@.*$", r"\1", line) for line in lines]


def ci_reason(before: str, after: str) -> str | None:
    kept = set(ci_lines(after))
    missing = [line for line in ci_lines(before) if line not in kept]
    if missing:
        return f"removes or renames a CI step, job, condition or path filter: `{missing[0]}`"
    return None


def verdict(tool: str, tool_input: dict, root: Path, config: dict) -> str | None:
    raw = tool_input.get("file_path")
    rel = teamlib.rel_path(str(raw), root) if raw else None
    if rel is None:
        return None
    path = root / rel
    rel = WORKTREE.sub("", rel)  # a file in an agent worktree follows the same rules
    before = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    if teamlib.matches(rel, config.get("protected_paths", [])):
        return f"{rel} is a protected path (generated, vendored or licensed)"
    if before is None:
        return None  # a new file weakens nothing
    if teamlib.matches(rel, config.get("append_only_paths", [])):
        return f"{rel} is append-only: add a new file, never change an existing one"
    after = after_edit(tool, tool_input, before)
    if teamlib.matches(rel, config.get("test_globs", [])):
        return test_reason(before, after, config)
    if teamlib.matches(rel, config.get("ci_paths", [])):
        return ci_reason(before, after)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        root = teamlib.work_dir(payload, teamlib.project_root(payload))
        config = teamlib.load_config(root)
    except Exception as exc:  # fail closed
        sys.stderr.write(f"BLOCKED: test guard could not read its input ({exc}).\n")
        return 2
    tool = payload.get("tool_name", "")
    if tool not in FILE_TOOLS:
        return 0
    reason = verdict(tool, payload.get("tool_input") or {}, root, config)
    if reason:
        sys.stderr.write(f"BLOCKED: {reason}. If the change is intended, the user makes it.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
