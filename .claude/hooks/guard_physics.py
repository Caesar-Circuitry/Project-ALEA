"""PreToolUse hook: block edits to the frozen shot-physics files.

Claude Code pipes the tool call as JSON on stdin. Exit 2 blocks the call and shows stderr to the
model. Set ALEA_ALLOW_PHYSICS_EDIT=1 to bypass (only with the user's explicit approval).
Pure stdlib so it runs on every platform via `uv run --no-project python`.
"""

import json
import os
import posixpath
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

FROZEN = ("alea/sim/shotsim.py", "alea/sim/study.py")
WRITE_VERBS = {"mv", "cp", "rm", "tee", "truncate", "dd", "install", "ln"}
REDIRECT_TOKEN = re.compile(r"^[0-9&]*>")
REDIRECT_PREFIX = re.compile(r"^[0-9&]*[<>]+&?")
SED_INPLACE = re.compile(r"^-[a-zA-Z]*i|^--in-place")
# Any of these can rewrite a file it names (perl -pi, python -c "open(..., 'w')", ...).
INTERPRETERS = {"python", "python3", "perl", "ruby", "node", "awk", "gawk", "php"}
# git subcommands that overwrite working-tree files named after them.
GIT_WRITE = {"checkout", "restore", "apply", "reset", "am", "cherry-pick", "revert", "stash"}


def _tokens(cmd: str) -> list[str]:
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return cmd.split()


def _cmd_name(tok: str) -> str:
    """`/usr/bin/python3.12` -> `python3`; `perl.exe` -> `perl`."""
    name = tok.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    return re.sub(r"(\d)\.\d+$", r"\1", name)


def _is_write(tokens: list[str]) -> bool:
    for i, tok in enumerate(tokens):
        if REDIRECT_TOKEN.match(tok):
            return True
        if _cmd_name(tok) in INTERPRETERS:
            return True
        if tok == "git" and any(t in GIT_WRITE for t in tokens[i + 1 :]):
            return True
        if tok in WRITE_VERBS and not (tok == "mv" and i > 0 and tokens[i - 1] == "git"):
            return True
        if tok == "sed" and any(SED_INPLACE.match(t) for t in tokens[i + 1 :]):
            return True
    return False


def _frozen_target(token: str, project_dir: Path) -> str | None:
    """The frozen file a shell token points at, resolved against the project dir."""
    candidates = {REDIRECT_PREFIX.sub("", token)}
    if "=" in token:
        candidates.add(token.split("=", 1)[1])
    root = project_dir.as_posix()
    for cand in candidates:
        if not cand:
            continue
        posix = cand.replace("\\", "/")
        if " " in posix and not posixpath.isabs(posix):
            continue  # quoted prose such as "see alea/sim/study.py", not a path
        full = posix if posixpath.isabs(posix) else f"{root}/{posix}"
        norm = posixpath.normpath(full)
        for f in FROZEN:
            if norm == f"{root}/{f}" or norm.endswith("/" + f):
                return f
    return None


def _inline_code_hit(tokens: list[str]) -> str | None:
    """A frozen path inside interpreter code, e.g. python -c "open('alea/sim/study.py','w')"."""
    if not any(_cmd_name(t) in INTERPRETERS for t in tokens):
        return None
    for tok in tokens:
        posix = tok.replace("\\", "/")
        for f in FROZEN:
            if f in posix:
                return f
    return None


def _bash_hit(cmd: str, project_dir: Path) -> str | None:
    tokens = _tokens(cmd)
    if not _is_write(tokens):
        return None
    for tok in tokens:
        hit = _frozen_target(tok, project_dir)
        if hit:
            return hit
    return _inline_code_hit(tokens)


def _norm(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _touches_frozen(text: str) -> str | None:
    norm = _norm(text)
    for f in FROZEN:
        if norm.endswith(f) or f in norm:
            return f
    return None


def main() -> int:
    if os.environ.get("ALEA_ALLOW_PHYSICS_EDIT") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
    except Exception as exc:  # fail closed: an unreadable call is not allowed through
        sys.stderr.write(f"BLOCKED: physics guard could not read the tool call ({exc}).\n")
        return 2
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    hit = None
    if tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        hit = _touches_frozen(str(target))
    elif tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd())
        hit = _bash_hit(cmd, project_dir)
    if hit:
        sys.stderr.write(
            f"BLOCKED: {hit} holds frozen shot physics (CLAUDE.md rule 1). "
            "Moving the file is fine via git mv; changing it needs the user's explicit approval, "
            "ALEA_ALLOW_PHYSICS_EDIT=1, a passing self-test and a Java comparison on the PR.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
