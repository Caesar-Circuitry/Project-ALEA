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
# token (subcommand); None means any arguments (read-only commands, checked further below).
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
        "merge-tree",
        "stash",
    },
    "gh": {"pr", "run", "api"},
}
READ_ONLY_CMDS = {
    "ls", "cat", "head", "tail", "grep", "rg", "find", "wc", "which", "type", "pwd", "echo",
    "tree", "cd", "sort", "uniq", "cut", "tr", "diff", "stat", "du", "file", "env", "printenv",
    "date", "true", "shasum", "sha256sum", "python", "python3",
}  # fmt: skip
for _cmd in READ_ONLY_CMDS:
    ALLOWED[_cmd] = None
UV_RUN_ALLOWED = {"pytest", "ruff", "pyright", "mkdocs", "pre-commit"}
RUFF_WRITE_FLAGS = {"--fix", "--unsafe-fixes"}
WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob", "xargs"}
FIND_WRITE = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
# `2>&1`, `>&2`, `>/dev/null`, `2>/dev/null` are harmless; every other redirect is a write/read.
SAFE_REDIRECT = re.compile(r">&[0-9]+|>>?\s*/dev/null\b")
GIT_LIST_FLAGS = {
    "-l", "--list", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--contains",
    "--no-contains", "--merged", "--no-merged", "--show-current", "--points-at",
    "--format", "--sort", "-n",
}  # fmt: skip
GIT_BRANCH_WRITE = {
    "-d", "-D", "-m", "-M", "-c", "-C", "-f", "-u", "--delete", "--move", "--copy", "--force",
    "--set-upstream-to", "--unset-upstream", "--edit-description",
}  # fmt: skip
GH_API_BODY_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}
BLOCK_MSG = (
    "BLOCKED for the lead: `{cmd}`. The lead coordinates and verifies; it does not write. "
    "Delegate code to `implementer`, docs to `docs-writer`, and use `/pr` to commit and push. "
    "Allowed here: just (not fmt), uv sync/lock, uv run pytest|ruff (no --fix)|pyright|mkdocs "
    "build|pre-commit run, read-only git (status/diff/log/branch/show/fetch/merge-tree/...), "
    "read-only gh (pr view|list|checks|diff, run list|view, api GET), and read-only shell "
    "commands without redirects (except 2>&1).\n"
)


def split_segments(cmd: str) -> list[str] | None:
    """Split on unquoted `;`, `&`, `&&`, `|`, `||` and newlines.

    Returns None when the command has an unsafe redirect or a command substitution, which the
    lead may not run. Quoted text (`"a\\|b"`) never splits. Harmless `2>&1`/`>/dev/null` are
    dropped from the segments.
    """
    segments: list[str] = []
    buf: list[str] = []
    quote = ""
    i, n = 0, len(cmd)

    def flush() -> None:
        segments.append("".join(buf))
        buf.clear()

    while i < n:
        c = cmd[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = ""
        elif quote == '"':
            if c == "\\" and i + 1 < n:
                buf.append(c + cmd[i + 1])
                i += 1
            else:
                if c == "`" or cmd.startswith("$(", i):
                    return None
                buf.append(c)
                if c == '"':
                    quote = ""
        elif c == "\\" and i + 1 < n:
            buf.append(c + cmd[i + 1])
            i += 1
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c == "`" or cmd.startswith("$(", i) or cmd.startswith("<(", i):
            return None
        elif c in ";\n|":
            flush()
        elif c == "&":
            if cmd.startswith("&>", i):
                return None
            flush()
        elif c in "<>":
            match = SAFE_REDIRECT.match(cmd, i) if c == ">" else None
            if not match:
                return None
            if buf and buf[-1].isdigit() and (len(buf) == 1 or buf[-2].isspace()):
                buf.pop()  # the fd number of `2>&1`
            i = match.end() - 1
        else:
            buf.append(c)
        i += 1
    if quote:
        return None
    flush()
    return segments


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


def _positional(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def _git_ok(args: list[str]) -> bool:
    i = 0
    while i < len(args):  # global options before the subcommand
        if args[i] in {"-C", "-c", "--git-dir", "--work-tree"}:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            break
    if i >= len(args) or args[i] not in ALLOWED["git"]:  # type: ignore[operator]
        return False
    sub, rest = args[i], args[i + 1 :]
    if any(a.startswith("--output") for a in rest):
        return False
    pos = _positional(rest)
    if sub == "branch":
        if any(a in GIT_BRANCH_WRITE for a in rest):
            return False
        listing = any(a.split("=")[0] in GIT_LIST_FLAGS for a in rest)
        return listing or not pos
    if sub == "tag":
        listing = any(a in {"-l", "--list", "-n"} for a in rest)
        return listing or not pos
    if sub == "worktree":
        return rest[:1] == ["list"]
    if sub == "remote":
        return not pos or pos[0] in {"show", "get-url"}
    if sub == "stash":
        return rest[:1] in (["list"], ["show"])
    if sub == "fetch":
        return True
    return True


def _gh_ok(args: list[str]) -> bool:
    if not args:
        return False
    if args[0] == "pr":
        return args[1:2] != [] and args[1] in {"view", "list", "checks", "diff"}
    if args[0] == "run":
        return args[1:2] != [] and args[1] in {"list", "view"}
    if args[0] == "api":
        rest = args[1:]
        method = ""
        for j, a in enumerate(rest):
            if a in {"-X", "--method"} and j + 1 < len(rest):
                method = rest[j + 1].upper()
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
            elif a.startswith("-X") and len(a) > 2:
                method = a[2:].upper()
        if method:
            return method == "GET"
        return not any(a in GH_API_BODY_FLAGS or a.startswith("--input=") for a in rest)
    return False


def _segment_ok(segment: str) -> bool:
    segment = segment.strip()
    if not segment:
        return True
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
    if cmd == "sort":
        return not any(a in {"-o", "--output"} or a.startswith("--output=") for a in args)
    if cmd == "env":
        return all(a.startswith("-") for a in args)  # `env CMD` would run CMD
    if cmd == "git":
        return _git_ok(args)
    if cmd == "gh":
        return _gh_ok(args)
    if cmd == "uv":
        if not args or args[0] not in sub:  # type: ignore[operator]
            return False
        if args[0] == "run":
            rest = [a for a in args[1:] if not a.startswith("-")]
            if not rest or rest[0] not in UV_RUN_ALLOWED:
                return False
            if rest[0] == "ruff" and any(a in RUFF_WRITE_FLAGS for a in args):
                return False
            if rest[0] == "ruff" and rest[1:2] == ["format"]:
                return "--check" in args or "--diff" in args
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


def command_ok(cmd: str) -> bool:
    segments = split_segments(cmd)
    return segments is not None and all(_segment_ok(seg) for seg in segments)


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
        if command_ok(cmd):
            return 0
        sys.stderr.write(BLOCK_MSG.format(cmd=cmd[:200]))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
