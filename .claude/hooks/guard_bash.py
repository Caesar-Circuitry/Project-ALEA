"""PreToolUse hook (Bash, every agent): commands no agent runs, and no way around the tests.

Blocks a command that (1) contains a `forbidden_commands` entry from `.claude/repo.json`,
(2) runs tests with a deselect or ignore flag, or (3) breaks a command-shape rule of the
rulebook. It checks the whole command text, so `just dev ...` and `bash -c '...'` wrappers are
covered. Exit 2 blocks the call and names the rule. Fails closed on unreadable input.
Pure stdlib.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teamlib

TEST_RUNNER = re.compile(r"\b(pytest|just\s+(dev\s+)?(test|gpu-test)|go\s+test|cargo\s+test)\b")
# Generic ways to make a test run pass by not running tests.
DESELECT = [
    ("--deselect", re.compile(r"--deselect\b")),
    ("--ignore", re.compile(r"--ignore(-glob)?\b")),
    ("-k not", re.compile(r"-k\s*=?\s*[\"']?\s*not\b")),
    ("--exclude", re.compile(r"--exclude\b")),
    (".skip", re.compile(r"\.skip\b")),
    ("-run '^$'", re.compile(r"-run\s+[\"']?\^\$")),
    ("-p no:", re.compile(r"-p\s+no:")),
    ("--collect-only as proof", re.compile(r"--(collect-only|co)\b.*&&")),
]
# One rule per line: (rule, rulebook heading, pattern).
SHAPE_RULES = [
    (
        "new branches use `git switch -c <name> --no-track origin/main`",
        "Rules Claude follows",
        re.compile(r"\bgit\s+(switch\s+(-c|-C|--create)|checkout\s+-[bB])\b(?!.*--no-track)"),
    ),
    (
        "pre-commit hooks are never skipped",
        "Rules Claude Code enforces",
        re.compile(r"\bSKIP=\S+.*\b(pre-commit|git\s+commit)\b"),
    ),
    (
        "golden data is never regenerated or replaced; ask the user for the file",
        "Rules Claude follows",
        re.compile(
            r"(np\.save|>>?|\b(cp|mv|rm|tee|dd|curl|wget)\b|\bgit\s+(checkout|restore)\b)"
            r".*golden_shots\.npy|golden_shots\.npy.*(np\.save|>>?)"
        ),
    ),
    (
        "secrets stay out of the shell: `.env` is not read",
        "Rules Claude follows",
        re.compile(r"\b(cat|less|more|head|tail|grep|rg|source|\.)\s+(\S*/)?\.env(\.local)?(\s|$)"),
    ),
]


def normalise(cmd: str) -> str:
    return re.sub(r"\s+", " ", cmd).strip()


def forbidden_hit(cmd: str, entries: list[str]) -> str | None:
    for entry in entries:
        needle = normalise(entry)
        if not needle:
            continue
        tail = "" if entry.endswith(" ") else r"(?![\w-])"
        pattern = r"(?<![\w./-])" + re.escape(needle) + tail
        if re.search(pattern, cmd + " " if entry.endswith(" ") else cmd):
            return entry.strip()
    return None


def verdict(cmd: str, config: dict) -> str | None:
    """The reason to block `cmd`, or None to allow it."""
    cmd = normalise(cmd)
    hit = forbidden_hit(cmd, config.get("forbidden_commands", []))
    if hit:
        return f"forbidden command `{hit}` (.claude/repo.json forbidden_commands)"
    if TEST_RUNNER.search(cmd):
        for name, pattern in DESELECT:
            if pattern.search(cmd):
                return (
                    f"test run with `{name}`: tests are not deselected or ignored to get green. "
                    "A failing test is fixed or reported as FAIL"
                )
    for rule, heading, pattern in SHAPE_RULES:
        if pattern.search(cmd):
            return f"{rule} (rulebook: {heading})"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        config = teamlib.load_config(teamlib.project_root(payload))
    except Exception as exc:  # fail closed
        sys.stderr.write(f"BLOCKED: bash guard could not read its input ({exc}).\n")
        return 2
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = str((payload.get("tool_input") or {}).get("command", ""))
    reason = verdict(cmd, config)
    if reason:
        sys.stderr.write(f"BLOCKED: {reason}.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
