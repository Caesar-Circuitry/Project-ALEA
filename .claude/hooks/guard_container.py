"""PreToolUse hook: every agent except the lead does its shell work inside the dev container.

The lead stays on the host. Any other agent (hook input `agent_type` present and not "lead") may
run Bash only as exactly one `just dev ...`, `just dev-status` or `docker exec alea-dev ...`
call, so its commands run in the sandbox with no push credentials. Compound commands go inside
the container: `just dev bash -c 'a && b'`. File tools may only touch paths inside the project
directory, and Read/Glob/Grep are confined to it plus the session scratchpad
(`<tmp>/claude-<uid>/`). Sessions without an `agent_type`, and the lead, are untouched.

Exit 2 blocks the call; stderr goes back to the model. Fails closed on unreadable input.
Set ALEA_ALLOW_HOST_AGENT_SHELL=1 to bypass (only with the user's explicit approval).
Pure stdlib.
"""

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# shared quote-aware tokeniser
from guard_lead import split_segments

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}
GLOB_META = re.compile(r"[*?\[{]")
CONTAINER = "alea-dev"
BLOCK_MSG = (
    "BLOCKED: `{cmd}` would run on the host. Agents other than the lead run shell commands "
    "inside the dev container: prefix with `just dev`, e.g. `just dev uv run pytest -q`, or "
    "`just dev bash -c 'cmd1 && cmd2'` for compound commands. If the container is not running, "
    "ask the user to run `just dev-up`. Only one `just dev ...`, `just dev-status` or "
    "`docker exec alea-dev ...` call per Bash command is allowed.\n"
)
PATH_MSG = (
    "BLOCKED: {path} is outside the project directory {root}. Agents other than the lead may "
    "only edit files inside the project.\n"
)


def _unquoted_dollar(cmd: str) -> bool:
    """True when `$` appears outside single quotes (the host shell would expand it)."""
    quote = ""
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if quote == "'":
            quote = "" if c == "'" else quote
        elif c == "\\" and i + 1 < len(cmd):
            i += 1
        elif c in "'\"":
            quote = c if not quote else ("" if quote == c else quote)
        elif c == "$" and quote != "'":
            return True
        i += 1
    return False


def command_ok(cmd: str) -> bool:
    segments = split_segments(cmd)
    if segments is None or len(segments) != 1 or _unquoted_dollar(cmd):
        return False
    try:
        tokens = shlex.split(segments[0])
    except ValueError:
        return False
    # `DEV_CWD=/workspace/sub just dev ...` may set the folder inside the container.
    while tokens and re.fullmatch(r"DEV_CWD=[^=]*", tokens[0]):
        tokens = tokens[1:]
    if tokens[:2] == ["just", "dev"]:
        return len(tokens) > 2
    if tokens[:2] == ["just", "dev-status"]:
        return len(tokens) == 2
    if tokens[:2] == ["docker", "exec"]:
        rest = tokens[2:]
        if rest[:1] == ["-w"]:  # working directory is the only option allowed
            rest = rest[2:]
        return rest[:1] == [CONTAINER] and len(rest) > 1
    return False


def _inside(target: Path, root: Path) -> bool:
    a, b = str(target), str(root)
    if os.name == "nt":
        a, b = a.lower(), b.lower()
    return a == b or a.startswith(b.rstrip("/\\") + os.sep)


def _scratch_root() -> Path | None:
    """The per-user Claude scratch area, e.g. /tmp/claude-1000 (not on Windows)."""
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return None
    return Path(tempfile.gettempdir(), f"claude-{getuid()}").resolve()


def path_ok(raw: str, project_dir: Path, allow_scratch: bool = False) -> bool:
    if not raw:
        return False
    try:
        root = project_dir.resolve()
        target = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()  # follows symlinks, collapses `..`
        if _inside(target, root):
            return True
        scratch = _scratch_root() if allow_scratch else None
        return scratch is not None and _inside(target, scratch)
    except Exception:
        return False


def _pattern_dir(pattern: str) -> str | None:
    """The fixed directory part of an absolute / `~` / `..` glob; None for a plain relative one."""
    if not (pattern.startswith(("/", "\\", "~", "..")) or re.match(r"[A-Za-z]:", pattern)):
        return None
    head = GLOB_META.split(pattern, 1)[0]
    return head if head != pattern else pattern


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
    except Exception as exc:  # fail closed: an unreadable call is not allowed through
        sys.stderr.write(f"BLOCKED: container guard could not read the tool call ({exc}).\n")
        return 2
    if os.environ.get("ALEA_ALLOW_HOST_AGENT_SHELL") == "1":
        return 0
    agent = payload.get("agent_type")
    if not agent or agent == "lead":
        return 0
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if command_ok(cmd):
            return 0
        sys.stderr.write(BLOCK_MSG.format(cmd=cmd[:200]))
        return 2
    if tool in FILE_TOOLS:
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd())
        raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if path_ok(raw, project):
            return 0
        sys.stderr.write(PATH_MSG.format(path=raw, root=project))
        return 2
    if tool in READ_TOOLS:
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd())
        targets = []
        if tool_input.get("file_path") or tool_input.get("path"):
            targets.append(str(tool_input.get("file_path") or tool_input.get("path")))
        for key in ("pattern", "glob"):
            if key == "pattern" and tool != "Glob":
                continue  # a Grep pattern is a regex, not a path
            head = _pattern_dir(str(tool_input.get(key) or ""))
            if head is not None:
                targets.append(head or "/")
        if tool == "Read" and not targets:
            targets.append("")  # a Read with no path is unreadable input: block
        for raw in targets:
            if not path_ok(raw, project, allow_scratch=True):
                sys.stderr.write(PATH_MSG.format(path=raw, root=project))
                return 2
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
