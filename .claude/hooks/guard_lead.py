"""PreToolUse hook: keep the `lead` agent coordinate-only.

The lead's tool list already removes Edit/Write. This hook covers the shell: only checks and
read-only git may run from the lead; anything that writes is delegated to a subagent. It acts
only when the hook input's `agent_type` is "lead" (the main session run via the `agent` setting
or `--agent lead`). Subagents and sessions started without the lead are untouched.

Exit 2 blocks the call; stderr goes back to the model. Pure stdlib.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# First token (after env assignments and wrappers) the lead may run. A set constrains the next
# token (subcommand); None means any arguments.
ALLOWED: dict[str, set[str] | None] = {
    "just": {
        "sync",
        "test",
        "selftest",
        "lint",
        "docs",
        "docs-serve",
        "robot",
        "gpu-test",
        "study",
        "default",
        "--list",
    },
    "uv": {"sync", "lock", "run", "tree", "version"},
    "git": {
        "status",
        "diff",
        "log",
        "branch",
        "show",
        "fetch",
        "ls-files",
        "rev-parse",
        "remote",
        "worktree",
        "hash-object",
        "blame",
        "describe",
        "tag",
    },
    "ls": None,
    "cat": None,
    "head": None,
    "tail": None,
    "grep": None,
    "rg": None,
    "find": None,
    "wc": None,
    "which": None,
    "pwd": None,
    "echo": None,
    "tree": None,
    "cd": None,
    "sort": None,
    "uniq": None,
    "cut": None,
    "diff": None,
    "stat": None,
    "du": None,
    "file": None,
    "env": None,
    "printenv": None,
    "date": None,
    "true": None,
    "python": None,
    "python3": None,
}
UV_RUN_ALLOWED = {"pytest", "ruff", "pyright", "mkdocs", "pre-commit"}
RUFF_WRITE_FLAGS = {"--fix", "--unsafe-fixes"}
WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob", "xargs"}
SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
REDIRECT = re.compile(r"(?<![0-9&<>])>>?(?!&)\s*(?!/dev/null\b)\S|(?<![0-9&<>])<(?![<&])\s*\S")
FIND_WRITE = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
BLOCK_MSG = (
    "BLOCKED for the lead: `{cmd}`. The lead coordinates and verifies; it does not write. "
    "Delegate code to `implementer`, docs to `docs-writer`, and use `/pr` to commit and push. "
    "Allowed here: just (not fmt), uv sync/lock, uv run pytest|ruff (no --fix)|pyright|mkdocs "
    "build|pre-commit run, read-only git (status/diff/log/branch/show/fetch), and read-only "
    "shell commands without redirects.\n"
)


def _strip_prefix(tokens: list[str]) -> list[str]:
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens = tokens[1:]
    while tokens and tokens[0] in WRAPPERS:
        wrapper = tokens[0]
        tokens = tokens[1:]
        if wrapper == "timeout" and tokens and tokens[0].isdigit():
            tokens = tokens[1:]
        elif wrapper == "nice" and tokens[:1] == ["-n"]:
            tokens = tokens[2:]
    return tokens


def _segment_ok(segment: str) -> bool:
    segment = segment.strip()
    if not segment:
        return True
    if REDIRECT.search(segment):
        return False
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False
    tokens = _strip_prefix(tokens)
    if not tokens:
        return True
    cmd, args = tokens[0], tokens[1:]
    if cmd not in ALLOWED:
        return False
    sub = ALLOWED[cmd]
    if cmd in {"python", "python3"}:
        return args[:1] in (["--version"], ["-V"])
    if cmd == "find":
        return not any(a in FIND_WRITE for a in args)
    if cmd == "uv":
        if not args or args[0] not in sub:
            return False
        if args[0] == "run":
            rest = [a for a in args[1:] if not a.startswith("-")]
            if not rest or rest[0] not in UV_RUN_ALLOWED:
                return False
            if rest[0] == "ruff" and any(a in RUFF_WRITE_FLAGS for a in args):
                return False
            if rest[0] == "mkdocs" and rest[1:2] != ["build"]:
                return False
            if rest[0] == "pre-commit" and rest[1:2] != ["run"]:
                return False
        return True
    if sub is not None:
        if cmd == "just" and not args:
            return True
        return bool(args) and args[0] in sub
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("agent_type") != "lead":
        return 0
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    if tool in FILE_TOOLS:
        sys.stderr.write(BLOCK_MSG.format(cmd=f"{tool} {tool_input.get('file_path', '')}"))
        return 2
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if all(_segment_ok(seg) for seg in SEPARATORS.split(cmd)):
            return 0
        sys.stderr.write(BLOCK_MSG.format(cmd=cmd[:200]))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
